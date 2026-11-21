// Navigation: 2 m nav grid, clearance, components, cover, A*, string pulling, local steering.
#include <algorithm>
#include <cmath>
#include <limits>
#include <queue>
#include <utility>

#include "internal.h"

static const int CLEAR_MAX_Q = 24;  // clearance cap: 24 * 0.25 = 6 m

static inline size_t lat(const MechCore* h, int i, int j) { return (size_t)j * h->tnx + i; }

// Can you walk from lattice point a to neighbouring lattice point b (height rules only)?
static inline bool lattice_step_ok(const MechCore* h, size_t a, size_t b, double steplen) {
    double rise = h->floor1[b] - h->floor1[a];
    if (rise <= 0) return true;  // drops of any height are fine (no fall damage)
    double thr = (h->onprism1[a] || h->onprism1[b]) ? h->step_up : h->slope_tan * steplen;
    return rise <= thr;
}

static inline bool passable(const MechCore* h, size_t c, double r) {
    return h->nclear[c] * 0.25 + 1e-6 >= r;
}

static bool can_move(const MechCore* h, int i, int j, int d, double r) {
    int ni = i + DIR_DX[d], nj = j + DIR_DY[d];
    if (ni < 0 || nj < 0 || ni >= h->nnx || nj >= h->nny) return false;
    size_t c = (size_t)j * h->nnx + i, n = (size_t)nj * h->nnx + ni;
    if (!(h->nedges[c] & (1 << d)) || !passable(h, n, r)) return false;
    if (DIR_DX[d] && DIR_DY[d]) {  // no corner cutting
        if (!passable(h, (size_t)j * h->nnx + ni, r) || !passable(h, (size_t)nj * h->nnx + i, r)) return false;
    }
    return true;
}

void build_nav(MechCore* h) {
    h->nnx = (h->tnx - 1) / 2 + 1;
    h->nny = (h->tny - 1) / 2 + 1;
    h->nres = h->tstep * 2;
    size_t nc = (size_t)h->nnx * h->nny;
    h->nfloor.assign(nc, 0);
    h->nedges.assign(nc, 0);
    h->nclear.assign(nc, 0);
    h->ncover.assign(nc, 0);
    h->ncomp.assign(nc, -1);

    for (int j = 0; j < h->nny; ++j)
        for (int i = 0; i < h->nnx; ++i) h->nfloor[(size_t)j * h->nnx + i] = h->floor1[lat(h, 2 * i, 2 * j)];

    // edges: two 1 m lattice sub-steps per 2 m move
    for (int j = 0; j < h->nny; ++j) {
        for (int i = 0; i < h->nnx; ++i) {
            uint8_t bits = 0;
            for (int d = 0; d < 8; ++d) {
                int li = 2 * i, lj = 2 * j;
                int ei = li + 2 * DIR_DX[d], ej = lj + 2 * DIR_DY[d];
                if (ei < 0 || ej < 0 || ei >= h->tnx || ej >= h->tny) continue;
                double sl = (DIR_DX[d] && DIR_DY[d]) ? 1.41421356 * h->tstep : h->tstep;
                size_t a = lat(h, li, lj), m = lat(h, li + DIR_DX[d], lj + DIR_DY[d]), b = lat(h, ei, ej);
                if (lattice_step_ok(h, a, m, sl) && lattice_step_ok(h, m, b, sl)) bits |= (uint8_t)(1 << d);
            }
            h->nedges[(size_t)j * h->nnx + i] = bits;
        }
    }

    // clearance: distance to the nearest lattice wall point higher than our floor + step_up
    const int R = (int)std::ceil(CLEAR_MAX_Q * 0.25 / h->tstep) + 1;
    std::vector<std::pair<float, std::pair<int, int>>> offs;
    for (int dj = -R; dj <= R; ++dj)
        for (int di = -R; di <= R; ++di) offs.push_back({(float)(std::sqrt(di * di + dj * dj) * h->tstep), {di, dj}});
    std::sort(offs.begin(), offs.end(), [](auto& a, auto& b) { return a.first < b.first; });
    for (int j = 0; j < h->nny; ++j) {
        for (int i = 0; i < h->nnx; ++i) {
            int li = 2 * i, lj = 2 * j;
            float f = h->floor1[lat(h, li, lj)];
            // map edge is a wall
            double edge = std::min({(double)li, (double)lj, (double)(h->tnx - 1 - li), (double)(h->tny - 1 - lj)}) * h->tstep;
            double clear = std::min(edge, CLEAR_MAX_Q * 0.25);
            for (auto& o : offs) {
                double d = o.first - 0.5 * h->tstep;
                if (d >= clear) break;
                int pi = li + o.second.first, pj = lj + o.second.second;
                if (pi < 0 || pj < 0 || pi >= h->tnx || pj >= h->tny) continue;
                size_t p = lat(h, pi, pj);
                if (h->wall1[p] && h->floor1[p] > f + h->step_up) { clear = std::max(0.0, d); break; }
            }
            h->nclear[(size_t)j * h->nnx + i] = (uint8_t)std::min(CLEAR_MAX_Q, (int)std::floor(clear * 4 + 1e-6));
        }
    }

    // static cover: 16 directions, anything rising above chest height within 6 m
    for (int j = 0; j < h->nny; ++j) {
        for (int i = 0; i < h->nnx; ++i) {
            size_t c = (size_t)j * h->nnx + i;
            if (h->nclear[c] == 0) continue;
            int li = 2 * i, lj = 2 * j;
            float f = h->floor1[lat(h, li, lj)];
            int cnt = 0;
            for (int k = 0; k < 16; ++k) {
                double a = k * MC_PI / 8, ca = std::cos(a), sa = std::sin(a);
                for (int s = 1; s <= 6; ++s) {
                    int pi = li + (int)std::lround(ca * s / h->tstep), pj = lj + (int)std::lround(sa * s / h->tstep);
                    if (pi < 0 || pj < 0 || pi >= h->tnx || pj >= h->tny) break;
                    if (h->floor1[lat(h, pi, pj)] > f + 4.5) { ++cnt; break; }
                }
            }
            h->ncover[c] = (uint8_t)cnt;
        }
    }

    // components over symmetric edges at the base radius
    int comp = 0, best_size = 0;
    std::vector<int> stack;
    for (size_t s = 0; s < nc; ++s) {
        if (h->ncomp[s] >= 0 || !passable(h, s, h->mech_r)) continue;
        int size = 0;
        stack.assign(1, (int)s);
        h->ncomp[s] = comp;
        while (!stack.empty()) {
            int c = stack.back(); stack.pop_back(); ++size;
            int i = c % h->nnx, j = c / h->nnx;
            for (int d = 0; d < 8; ++d) {
                if (!can_move(h, i, j, d, h->mech_r)) continue;
                int n = (j + DIR_DY[d]) * h->nnx + (i + DIR_DX[d]);
                int back = (d + 4) & 7;
                if (h->ncomp[n] >= 0 || !can_move(h, i + DIR_DX[d], j + DIR_DY[d], back, h->mech_r)) continue;
                h->ncomp[n] = comp;
                stack.push_back(n);
            }
        }
        if (size > best_size) { best_size = size; h->ground_comp = comp; }
        ++comp;
    }

    h->g.assign(nc, 0);
    h->parent.assign(nc, -1);
    h->gen.assign(nc, 0);
    h->closed_gen.assign(nc, 0);
    h->tcnx = (h->nnx + 3) / 4;
    h->tcny = (h->nny + 3) / 4;
    h->threat_cache.assign((size_t)h->tcnx * h->tcny * 8, 0);
    h->threat_gen.assign((size_t)h->tcnx * h->tcny, 0);
    h->cur_gen = 0;
}

// Nearest nav cell passable at radius r (optionally in the ground component). Returns cell or -1.
static int nearest_cell(const MechCore* h, double x, double y, double r, bool ground_only, int max_ring) {
    int ci = (int)std::lround((x - h->tminx) / h->nres), cj = (int)std::lround((y - h->tminy) / h->nres);
    ci = std::min(std::max(ci, 0), h->nnx - 1);
    cj = std::min(std::max(cj, 0), h->nny - 1);
    auto ok = [&](int i, int j) {
        size_t c = (size_t)j * h->nnx + i;
        return passable(h, c, r) && (!ground_only || h->ncomp[c] == h->ground_comp);
    };
    int best = -1;
    double bd = std::numeric_limits<double>::infinity();
    for (int k = 0; k <= max_ring; ++k) {
        for (int dj = -k; dj <= k; ++dj) {
            for (int di = -k; di <= k; ++di) {
                if (std::max(std::abs(di), std::abs(dj)) != k) continue;
                int i = ci + di, j = cj + dj;
                if (i < 0 || j < 0 || i >= h->nnx || j >= h->nny || !ok(i, j)) continue;
                double dx = nav_x(h, i) - x, dy = nav_y(h, j) - y, d = dx * dx + dy * dy;
                if (d < bd) { bd = d; best = j * h->nnx + i; }
            }
        }
        // a cell found on ring k may be beaten by one on ring k+1 (corners); stop one ring later
        if (best >= 0 && k * h->nres > std::sqrt(bd) + h->nres) break;
    }
    return best;
}

static bool segment_ok(const MechCore* h, double ax, double ay, double bx, double by, double r) {
    double dx = bx - ax, dy = by - ay, len = std::sqrt(dx * dx + dy * dy);
    int n = std::max(1, (int)std::ceil(len / h->tstep));
    size_t prev = SIZE_MAX;
    for (int k = 0; k <= n; ++k) {
        double t = (double)k / n, x = ax + t * dx, y = ay + t * dy;
        int i, j;
        if (!nav_cell(h, x, y, &i, &j)) return false;
        if (!passable(h, (size_t)j * h->nnx + i, r)) return false;
        int li = (int)std::lround((x - h->tminx) / h->tstep), lj = (int)std::lround((y - h->tminy) / h->tstep);
        li = std::min(std::max(li, 0), h->tnx - 1);
        lj = std::min(std::max(lj, 0), h->tny - 1);
        size_t p = lat(h, li, lj);
        if (prev != SIZE_MAX && p != prev && !lattice_step_ok(h, prev, p, len / n)) return false;
        prev = p;
    }
    return true;
}

extern "C" {

MC_API int mc_nearest_walkable(MechCore* h, double x, double y, double radius, int ground_only, double* out_xy) {
    if (!h->built) return 0;
    int c = nearest_cell(h, x, y, radius, ground_only != 0, 80);
    if (c < 0) return 0;
    out_xy[0] = nav_x(h, c % h->nnx);
    out_xy[1] = nav_y(h, c / h->nnx);
    return 1;
}

MC_API int mc_segment_walkable(MechCore* h, double ax, double ay, double bx, double by, double radius) {
    return h->built && segment_ok(h, ax, ay, bx, by, radius) ? 1 : 0;
}

MC_API int mc_find_path(MechCore* h, double sx, double sy, double gx, double gy, double radius,
                        const double* threats, int n_threats, const double* zone,
                        double cover_weight, double h_weight, int max_expansions, double* out_xy, int max_pts) {
    if (!h->built || max_pts < 1) return -1;
    if (h_weight < 1.0) h_weight = 1.0;
    n_threats = std::min(std::max(n_threats, 0), 8);
    int start = nearest_cell(h, sx, sy, radius, false, 10);
    if (start < 0) return -1;
    bool ground = h->ncomp[start] == h->ground_comp;
    int goal = nearest_cell(h, gx, gy, radius, ground, 80);
    if (goal < 0) goal = nearest_cell(h, gx, gy, radius, false, 80);
    if (goal < 0) return -2;

    if (++h->cur_gen == 0) {
        std::fill(h->gen.begin(), h->gen.end(), 0);
        std::fill(h->closed_gen.begin(), h->closed_gen.end(), 0);
        std::fill(h->threat_gen.begin(), h->threat_gen.end(), 0);
        h->cur_gen = 1;
    }
    const uint32_t G = h->cur_gen;
    const int nnx = h->nnx;
    const double gxc = nav_x(h, goal % nnx), gyc = nav_y(h, goal / nnx);
    int los_budget = 1500;

    // threat eye heights (floor at the threat + 8 m)
    double teye[8];
    for (int k = 0; k < n_threats; ++k) teye[k] = floor_at(h, threats[4 * k], threats[4 * k + 1], nullptr, nullptr) + 8.0;

    auto cell_mult = [&](int c) {
        double x = nav_x(h, c % nnx), y = nav_y(h, c / nnx);
        double m = 1.0 - cover_weight * (h->ncover[c] / 16.0);
        if (zone) {
            double dx = x - zone[0], dy = y - zone[1];
            if (dx * dx + dy * dy > zone[2] * zone[2]) m += zone[3];
        }
        if (n_threats) {
            // visibility is cached per 8 m block (4x4 nav cells), sampled at the block centre
            int bi = (c % nnx) >> 2, bj = (c / nnx) >> 2;
            size_t blk = (size_t)bj * h->tcnx + bi;
            if (h->threat_gen[blk] != G) {
                h->threat_gen[blk] = G;
                int ci = std::min(bi * 4 + 2, h->nnx - 1), cj = std::min(bj * 4 + 2, h->nny - 1);
                double bx = nav_x(h, ci), by = nav_y(h, cj);
                double bz = h->nfloor[(size_t)cj * nnx + ci] + 4.5;
                for (int k = 0; k < n_threats; ++k) {
                    const double* t = threats + 4 * k;
                    double dx = bx - t[0], dy = by - t[1];
                    bool seen = true;
                    if (dx * dx + dy * dy < (t[2] + 6) * (t[2] + 6) && los_budget > 0) {
                        --los_budget;
                        seen = vision_ray(h, t[0], t[1], teye[k], bx, by, bz);
                    }
                    h->threat_cache[blk * 8 + k] = seen ? 1.f : 0.f;
                }
            }
            for (int k = 0; k < n_threats; ++k) {
                if (h->threat_cache[blk * 8 + k] == 0.f) continue;
                const double* t = threats + 4 * k;
                double dx = x - t[0], dy = y - t[1], d = std::sqrt(dx * dx + dy * dy);
                if (d < t[2]) m += t[3] * (1.0 - d / t[2]);
            }
        }
        return std::max(0.3, m);
    };
    auto heur = [&](int c) {
        double dx = std::abs(nav_x(h, c % nnx) - gxc), dy = std::abs(nav_y(h, c / nnx) - gyc);
        return h_weight * (std::max(dx, dy) + 0.41421356 * std::min(dx, dy));
    };

    typedef std::pair<float, int> QE;
    std::priority_queue<QE, std::vector<QE>, std::greater<QE>> open;
    h->gen[start] = G;
    h->g[start] = 0;
    h->parent[start] = -1;
    open.push({(float)heur(start), start});
    int best = start;
    double best_h = heur(start);
    int expansions = 0;
    bool found = false;
    while (!open.empty()) {
        int c = open.top().second;
        open.pop();
        if (h->closed_gen[c] == G) continue;
        h->closed_gen[c] = G;
        if (c == goal) { found = true; break; }
        double hc = heur(c);
        if (hc < best_h) { best_h = hc; best = c; }
        if (++expansions > max_expansions) break;
        int i = c % nnx, j = c / nnx;
        for (int d = 0; d < 8; ++d) {
            if (!can_move(h, i, j, d, radius)) continue;
            int n = (j + DIR_DY[d]) * nnx + (i + DIR_DX[d]);
            if (h->closed_gen[n] == G) continue;
            double step = ((DIR_DX[d] && DIR_DY[d]) ? 1.41421356 : 1.0) * h->nres;
            double ng = h->g[c] + step * cell_mult(n);
            if (h->gen[n] != G || ng < h->g[n]) {
                h->gen[n] = G;
                h->g[n] = (float)ng;
                h->parent[n] = c;
                open.push({(float)(ng + heur(n)), n});
            }
        }
    }
    int end = found ? goal : best;
    if (end == start && !found) return -3;

    // reconstruct
    std::vector<int> cells;
    for (int c = end; c >= 0; c = h->parent[c]) cells.push_back(c);
    std::reverse(cells.begin(), cells.end());
    std::vector<std::pair<double, double>> pts;
    for (int c : cells) pts.push_back({nav_x(h, c % nnx), nav_y(h, c / nnx)});
    if (found) {
        int gi, gj;
        if (nav_cell(h, gx, gy, &gi, &gj) && gj * nnx + gi == goal) pts.back() = {gx, gy};
    }

    // string pulling: from each anchor, jump to the farthest point within 24 m with a walkable segment
    std::vector<std::pair<double, double>> out;
    size_t a = 0;
    std::pair<double, double> anchor = {sx, sy};
    while (a + 1 < pts.size()) {
        size_t far = a + 1;
        for (size_t k = pts.size() - 1; k > a + 1; --k) {
            double dx = pts[k].first - anchor.first, dy = pts[k].second - anchor.second;
            if (dx * dx + dy * dy > 24.0 * 24.0) continue;
            if (segment_ok(h, anchor.first, anchor.second, pts[k].first, pts[k].second, radius)) { far = k; break; }
        }
        out.push_back(pts[far]);
        anchor = pts[far];
        a = far;
    }
    if (out.empty()) out.push_back(pts.back());
    int n = (int)std::min(out.size(), (size_t)max_pts);
    for (int k = 0; k < n; ++k) { out_xy[2 * k] = out[k].first; out_xy[2 * k + 1] = out[k].second; }
    return n;
}

MC_API int mc_steer(MechCore* h, double px, double py, double wx, double wy, double radius,
                    double speed, const double* zone, const double* shells, int n_shells,
                    const double* weights, double* out) {
    double wa = 1.0, wc = 0.8, wz = 1.5, ws = 3.0;
    if (weights) { wa = weights[0]; wc = weights[1]; wz = weights[2]; ws = weights[3]; }
    double tx = wx - px, ty = wy - py, tl = std::sqrt(tx * tx + ty * ty);
    if (tl > 1e-6) { tx /= tl; ty /= tl; }
    int best = 0;
    double best_s = -std::numeric_limits<double>::infinity(), bdx = 0, bdy = 0;
    for (int k = 0; k < 16; ++k) {
        double a = k * MC_PI / 8, dx = std::cos(a), dy = std::sin(a);
        double align = tl > 1e-6 ? dx * tx + dy * ty : 0.0;
        // free distance along the probe (0..5 m)
        double free_d = 0;
        if (h->built) {
            size_t prev = SIZE_MAX;
            for (int s = 0; s <= 5; ++s) {
                double x = px + dx * s, y = py + dy * s;
                int i, j;
                if (!nav_cell(h, x, y, &i, &j) || !passable(h, (size_t)j * h->nnx + i, radius)) break;
                int li = std::min(std::max((int)std::lround((x - h->tminx) / h->tstep), 0), h->tnx - 1);
                int lj = std::min(std::max((int)std::lround((y - h->tminy) / h->tstep), 0), h->tny - 1);
                size_t p = lat(h, li, lj);
                if (prev != SIZE_MAX && p != prev && !lattice_step_ok(h, prev, p, 1.0)) break;
                prev = p;
                free_d = s;
            }
        } else {
            free_d = 5;
        }
        double out_z = 0;
        if (zone) {
            double qx = px + dx * 4 - zone[0], qy = py + dy * 4 - zone[1];
            out_z = std::min(1.0, std::max(0.0, std::sqrt(qx * qx + qy * qy) - zone[2]) / 4.0);
        }
        double shell_pen = 0;
        for (int s = 0; s < n_shells; ++s) {
            const double* sh = shells + 4 * s;
            double t = std::min(std::max(sh[3], 0.0), 2.0);
            double qx = px + dx * speed * t - sh[0], qy = py + dy * speed * t - sh[1];
            double d = std::sqrt(qx * qx + qy * qy);
            if (d < sh[2]) shell_pen += 1.0 - d / sh[2];
        }
        double score = wa * align + wc * (free_d / 5.0) - wz * out_z - ws * shell_pen;
        if (score > best_s) { best_s = score; best = k; bdx = dx; bdy = dy; }
    }
    if (out) { out[0] = bdx; out[1] = bdy; out[2] = best_s; }
    return best;
}

}  // extern "C"
