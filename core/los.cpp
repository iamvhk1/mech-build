// Line of sight: shot rays (buildings, bridges, terrain) and vision rays (+ trunks, canopy).
#include <algorithm>
#include <cmath>
#include <limits>

#include "internal.h"

// Visit broad-phase buckets along a 2D segment (Amanatides-Woo DDA). f(bucket) returns false to stop.
template <class F>
static void dda(const MechCore* h, double ax, double ay, double bx, double by, F f) {
    double fx = (ax - h->bminx) / h->bcell, fy = (ay - h->bminy) / h->bcell;
    double gx = (bx - h->bminx) / h->bcell, gy = (by - h->bminy) / h->bcell;
    int i = (int)std::floor(fx), j = (int)std::floor(fy);
    int ie = (int)std::floor(gx), je = (int)std::floor(gy);
    double dx = gx - fx, dy = gy - fy;
    int sx = dx > 0 ? 1 : (dx < 0 ? -1 : 0), sy = dy > 0 ? 1 : (dy < 0 ? -1 : 0);
    const double INF = std::numeric_limits<double>::infinity();
    double tdx = sx ? std::abs(1.0 / dx) : INF, tdy = sy ? std::abs(1.0 / dy) : INF;
    double tmx = sx > 0 ? (i + 1 - fx) * tdx : (sx < 0 ? (fx - i) * tdx : INF);
    double tmy = sy > 0 ? (j + 1 - fy) * tdy : (sy < 0 ? (fy - j) * tdy : INF);
    int guard = std::abs(ie - i) + std::abs(je - j) + 2;
    for (int k = 0; k <= guard; ++k) {
        if (i >= 0 && j >= 0 && i < h->bnx && j < h->bny) {
            if (!f((size_t)j * h->bnx + i)) return;
        }
        if (i == ie && j == je) return;
        if (tmx < tmy) { i += sx; tmx += tdx; } else { j += sy; tmy += tdy; }
    }
}

// First hit parameter of segment (p0 + u*(p1-p0)), u in [0,1], against a prism's 2D outline.
static double prism_hit_u(const Prism& p, double x0, double y0, double x1, double y1) {
    if (point_in_prism2d(p, x0, y0)) return 0.0;
    double best = 2.0;
    double rx = x1 - x0, ry = y1 - y0;
    if (rx * rx + ry * ry < 1e-12) return best;
    const float* e = p.edges.data();
    size_t n = p.edges.size() / 4;
    for (size_t k = 0; k < n; ++k, e += 4) {
        double sx = e[2] - e[0], sy = e[3] - e[1];
        double den = rx * sy - ry * sx;
        if (std::abs(den) < 1e-12) continue;
        double qx = e[0] - x0, qy = e[1] - y0;
        double u = (qx * sy - qy * sx) / den;
        if (u < 0 || u > 1 || u >= best) continue;
        double v = (qx * ry - qy * rx) / den;
        if (v < 0 || v > 1) continue;
        best = u;
    }
    return best;
}

double shot_ray(MechCore* h, double ax, double ay, double az, double bx, double by, double bz) {
    double best = 1.0;
    double dx = bx - ax, dy = by - ay, dz = bz - az;
    double minx = std::min(ax, bx), maxx = std::max(ax, bx);
    double miny = std::min(ay, by), maxy = std::max(ay, by);

    // prisms
    uint32_t st = ++h->stamp;
    if (st == 0) { std::fill(h->pstamp.begin(), h->pstamp.end(), 0); std::fill(h->tstamp.begin(), h->tstamp.end(), 0); st = h->stamp = 1; }
    dda(h, ax, ay, bx, by, [&](size_t b) {
        for (int idx : h->pbuckets[b]) {
            if (h->pstamp[idx] == st) continue;
            h->pstamp[idx] = st;
            const Prism& p = h->prisms[idx];
            if (p.maxx < minx || p.minx > maxx || p.maxy < miny || p.miny > maxy) continue;
            double t0 = 0, t1 = 1;
            if (std::abs(dz) < 1e-9) {
                if (az < p.base || az > p.top) continue;
            } else {
                double ta = (p.base - az) / dz, tb = (p.top - az) / dz;
                t0 = std::max(0.0, std::min(ta, tb));
                t1 = std::min(1.0, std::max(ta, tb));
                if (t0 > t1) continue;
            }
            if (t0 >= best) continue;
            // Liang-Barsky: clip [t0, t1] to the prism's 2D bounding box
            {
                const double pd[4] = {-dx, dx, -dy, dy};
                const double qd[4] = {ax - p.minx, p.maxx - ax, ay - p.miny, p.maxy - ay};
                bool out = false;
                for (int e = 0; e < 4 && !out; ++e) {
                    if (std::abs(pd[e]) < 1e-12) { out = qd[e] < 0; continue; }
                    double r = qd[e] / pd[e];
                    if (pd[e] < 0) { if (r > t0) t0 = r; } else { if (r < t1) t1 = r; }
                    out = t0 > t1;
                }
                if (out || t0 >= best) continue;
            }
            double u = prism_hit_u(p, ax + t0 * dx, ay + t0 * dy, ax + t1 * dx, ay + t1 * dy);
            if (u <= 1.0) best = std::min(best, t0 + u * (t1 - t0));
        }
        return true;
    });

    // terrain: walk 2 m coarse steps; fine-sample (0.75 m) only where the line dips below the
    // highest ground of the 4 m blocks it crosses. Endpoints are excluded (targets stand on ground).
    if (std::min(az, bz) <= h->terr_max) {
        double len = std::sqrt(dx * dx + dy * dy);
        int nc = std::max(1, (int)std::ceil(len / 2.0));
        double fine = 1.0 / std::max(2, (int)std::ceil(len / (h->tstep * 0.75)));
        // 8 m outer steps against 16 m block maxima; 2 m inner steps only where needed
        const int per = 4;
        for (int k = 0; k < nc; ++k) {
            double ta = (double)k / nc, tb = (double)(k + 1) / nc;
            if (ta >= best) break;
            if (k % per == 0) {
                double ua = ta, ub = std::min(1.0, (double)(k + per) / nc), um = 0.5 * (ua + ub);
                double zlo = std::min(az + ua * dz, az + ub * dz);
                double m16 = std::max({coarse_max16(h, ax + ua * dx, ay + ua * dy), coarse_max16(h, ax + ub * dx, ay + ub * dy),
                                       coarse_max16(h, ax + um * dx, ay + um * dy)});
                if (zlo > m16) { k += per - 1; continue; }
            }
            double zmin = std::min(az + ta * dz, az + tb * dz);
            double tm = 0.5 * (ta + tb);
            double cm = std::max({coarse_max(h, ax + ta * dx, ay + ta * dy), coarse_max(h, ax + tb * dx, ay + tb * dy),
                                  coarse_max(h, ax + tm * dx, ay + tm * dy)});
            if (zmin > cm) continue;
            bool hit = false;
            for (double t = std::ceil(ta / fine) * fine; t <= tb + 1e-12; t += fine) {
                if (t <= 1e-9) continue;
                if (t >= 1.0 - 1e-9 || t >= best) break;
                if (az + t * dz < terrain_z(h, ax + t * dx, ay + t * dy)) {
                    best = std::max(0.0, t - fine);
                    hit = true;
                    break;
                }
            }
            if (hit) break;
        }
    }
    return best;
}

bool vision_ray(MechCore* h, double ax, double ay, double az, double bx, double by, double bz) {
    if (shot_ray(h, ax, ay, az, bx, by, bz) < 1.0 - 1e-6) return false;
    double dx = bx - ax, dy = by - ay, dz = bz - az;
    double len = std::sqrt(dx * dx + dy * dy + dz * dz);
    double len2d2 = dx * dx + dy * dy;
    double max_chord = std::log(1.0 / std::max(1e-6, h->canopy_block_t)) / std::max(1e-6, h->canopy_density);
    double chord = 0;
    bool blocked = false;
    uint32_t st = ++h->stamp;
    if (st == 0) { std::fill(h->pstamp.begin(), h->pstamp.end(), 0); std::fill(h->tstamp.begin(), h->tstamp.end(), 0); st = h->stamp = 1; }
    dda(h, ax, ay, bx, by, [&](size_t b) {
        for (int idx : h->tbuckets[b]) {
            if (h->tstamp[idx] == st) continue;
            h->tstamp[idx] = st;
            const Tree& t = h->trees[idx];
            // trunk: vertical cylinder from the ground to the crown base
            if (len2d2 > 1e-12) {
                double u = ((t.x - ax) * dx + (t.y - ay) * dy) / len2d2;
                u = std::min(1.0, std::max(0.0, u));
                double px = ax + u * dx - t.x, py = ay + u * dy - t.y;
                double pz = az + u * dz;
                if (px * px + py * py < (double)t.trunk_r * t.trunk_r && pz >= t.z && pz <= t.z + t.crown_base) {
                    blocked = true;
                    return false;
                }
            }
            // crown: ellipsoid, accumulate chord length
            double ox = (ax - t.cx) / t.crown_r, oy = (ay - t.cy) / t.crown_r, oz = (az - t.crown_cz) / t.crown_hz;
            double vx = dx / t.crown_r, vy = dy / t.crown_r, vz = dz / t.crown_hz;
            double A = vx * vx + vy * vy + vz * vz;
            double B = 2 * (ox * vx + oy * vy + oz * vz);
            double C = ox * ox + oy * oy + oz * oz - 1;
            double disc = B * B - 4 * A * C;
            if (A < 1e-12 || disc <= 0) continue;
            double sq = std::sqrt(disc);
            double t0 = std::max(0.0, (-B - sq) / (2 * A)), t1 = std::min(1.0, (-B + sq) / (2 * A));
            if (t1 > t0) {
                chord += (t1 - t0) * len;
                if (chord > max_chord) { blocked = true; return false; }
            }
        }
        return true;
    });
    return !blocked;
}

extern "C" {

MC_API double mc_shot_los(MechCore* h, double ax, double ay, double az, double bx, double by, double bz) {
    return shot_ray(h, ax, ay, az, bx, by, bz);
}

MC_API int mc_vision_los(MechCore* h, double ax, double ay, double az, double bx, double by, double bz) {
    return vision_ray(h, ax, ay, az, bx, by, bz) ? 1 : 0;
}

MC_API void mc_shot_los_batch(MechCore* h, int n, const double* s, double* out) {
    for (int k = 0; k < n; ++k, s += 6) out[k] = shot_ray(h, s[0], s[1], s[2], s[3], s[4], s[5]);
}

MC_API void mc_vision_los_batch(MechCore* h, int n, const double* s, uint8_t* out) {
    for (int k = 0; k < n; ++k, s += 6) out[k] = vision_ray(h, s[0], s[1], s[2], s[3], s[4], s[5]) ? 1 : 0;
}

MC_API int mc_can_see(MechCore* h, double ox, double oy, double eye_z, double aim_yaw,
                      double tx, double ty, double cz, double topz,
                      double near_range, double range, double fov_deg) {
    double dx = tx - ox, dy = ty - oy, dz = cz - eye_z;
    double d = std::sqrt(dx * dx + dy * dy + dz * dz);
    if (d <= near_range) {
        // proximity sensors: buildings block, canopy does not
        return (shot_ray(h, ox, oy, eye_z, tx, ty, cz) >= 1.0 - 1e-6 ||
                shot_ray(h, ox, oy, eye_z, tx, ty, topz) >= 1.0 - 1e-6) ? 1 : 0;
    }
    if (d > range) return 0;
    double yaw = std::atan2(dy, dx);
    double diff = std::remainder(yaw - aim_yaw, 2 * MC_PI);
    if (std::abs(diff) > fov_deg * MC_PI / 360.0) return 0;
    return (vision_ray(h, ox, oy, eye_z, tx, ty, cz) || vision_ray(h, ox, oy, eye_z, tx, ty, topz)) ? 1 : 0;
}

}  // extern "C"
