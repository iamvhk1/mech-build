// Map model: terrain, prisms, trees, floor model, build entry point and point queries.
#include <algorithm>
#include <chrono>
#include <limits>
#include <utility>

#include "internal.h"

// ---------------------------------------------------------------- terrain

double terrain_z(const MechCore* h, double x, double y) {
    if (h->terr.empty()) return 0.0;
    double fx = (x - h->tminx) / h->tstep, fy = (y - h->tminy) / h->tstep;
    fx = std::min(std::max(fx, 0.0), (double)(h->tnx - 1));
    fy = std::min(std::max(fy, 0.0), (double)(h->tny - 1));
    int i = std::min((int)fx, h->tnx - 2), j = std::min((int)fy, h->tny - 2);
    double u = fx - i, v = fy - j;
    const float* r0 = &h->terr[(size_t)j * h->tnx + i];
    const float* r1 = r0 + h->tnx;
    return (r0[0] * (1 - u) + r0[1] * u) * (1 - v) + (r1[0] * (1 - u) + r1[1] * u) * v;
}

// ---------------------------------------------------------------- prisms

bool point_in_prism2d(const Prism& p, double x, double y) {
    if (x < p.minx || x > p.maxx || y < p.miny || y > p.maxy) return false;
    bool in = false;
    const float* e = p.edges.data();
    size_t n = p.edges.size() / 4;
    for (size_t k = 0; k < n; ++k, e += 4) {
        double y0 = e[1], y1 = e[3];
        if ((y0 > y) != (y1 > y)) {
            double xi = e[0] + (y - y0) * (e[2] - e[0]) / (y1 - y0);
            if (x < xi) in = !in;
        }
    }
    return in;
}

// Ground-layer standing height at a point. Slabs sorted by base: a prism we cannot fit under
// becomes floor (its top), one at least a mech-height above the current floor is walked under.
// kind: 0 terrain, else prism kind + 1 (1 building, 2 stadium, 3 bridge).
static double apply_floor_rule(const MechCore* h, double ground, std::vector<Slab>& bt,
                               uint8_t* kind, double* overhead) {
    std::sort(bt.begin(), bt.end(), [](const Slab& a, const Slab& b) { return a.base < b.base; });
    double s = ground, over = std::numeric_limits<double>::infinity();
    uint8_t k = 0;
    for (auto& q : bt) {
        if (q.base >= s + h->mech_h - 0.01) { over = q.base; break; }
        if (q.top > s) { s = q.top; k = (uint8_t)(q.kind + 1); }
    }
    if (kind) *kind = k;
    if (overhead) *overhead = over;
    return s;
}

double floor_at(const MechCore* h, double x, double y, bool* on_prism, double* overhead) {
    double gz = terrain_z(h, x, y);
    int bi, bj;
    int b = bucket_of(h, x, y, &bi, &bj);
    std::vector<Slab> bt;
    if (b >= 0) {
        for (int idx : h->pbuckets[b]) {
            const Prism& p = h->prisms[idx];
            if (point_in_prism2d(p, x, y)) bt.push_back({p.base, p.top, p.kind});
        }
    }
    uint8_t k;
    double f = apply_floor_rule(h, gz, bt, &k, overhead);
    if (on_prism) *on_prism = k != 0;
    return f;
}

void build_buckets(MechCore* h) {
    h->bminx = h->tminx;
    h->bminy = h->tminy;
    h->bnx = (int)std::ceil((h->tnx - 1) * h->tstep / h->bcell) + 1;
    h->bny = (int)std::ceil((h->tny - 1) * h->tstep / h->bcell) + 1;
    size_t nb = (size_t)h->bnx * h->bny;
    h->pbuckets.assign(nb, {});
    h->tbuckets.assign(nb, {});
    auto add = [&](std::vector<std::vector<int>>& bk, int idx, double x0, double y0, double x1, double y1) {
        int i0 = std::max(0, (int)std::floor((x0 - h->bminx) / h->bcell));
        int j0 = std::max(0, (int)std::floor((y0 - h->bminy) / h->bcell));
        int i1 = std::min(h->bnx - 1, (int)std::floor((x1 - h->bminx) / h->bcell));
        int j1 = std::min(h->bny - 1, (int)std::floor((y1 - h->bminy) / h->bcell));
        for (int j = j0; j <= j1; ++j)
            for (int i = i0; i <= i1; ++i) bk[(size_t)j * h->bnx + i].push_back(idx);
    };
    for (size_t k = 0; k < h->prisms.size(); ++k) {
        const Prism& p = h->prisms[k];
        add(h->pbuckets, (int)k, p.minx, p.miny, p.maxx, p.maxy);
    }
    for (size_t k = 0; k < h->trees.size(); ++k) {
        const Tree& t = h->trees[k];
        add(h->tbuckets, (int)k, t.minx, t.miny, t.maxx, t.maxy);
    }
    h->pstamp.assign(h->prisms.size(), 0);
    h->tstamp.assign(h->trees.size(), 0);
}

// Rasterize every prism onto the terrain lattice with a scanline (even-odd over ring + holes),
// then apply the floor rule per lattice point.
static void build_floor(MechCore* h) {
    size_t n = (size_t)h->tnx * h->tny;
    std::vector<std::pair<int, int>> cover;  // (lattice index, prism index)
    cover.reserve(400000);
    std::vector<double> xs;
    for (size_t k = 0; k < h->prisms.size(); ++k) {
        const Prism& p = h->prisms[k];
        int j0 = std::max(0, (int)std::ceil((p.miny - h->tminy) / h->tstep));
        int j1 = std::min(h->tny - 1, (int)std::floor((p.maxy - h->tminy) / h->tstep));
        size_t ne = p.edges.size() / 4;
        for (int j = j0; j <= j1; ++j) {
            double y = h->tminy + j * h->tstep;
            xs.clear();
            const float* e = p.edges.data();
            for (size_t q = 0; q < ne; ++q, e += 4) {
                double ya = e[1], yb = e[3];
                if ((ya > y) != (yb > y)) xs.push_back(e[0] + (y - ya) * (e[2] - e[0]) / (yb - ya));
            }
            std::sort(xs.begin(), xs.end());
            for (size_t q = 0; q + 1 < xs.size(); q += 2) {
                int i0 = std::max(0, (int)std::ceil((xs[q] - h->tminx) / h->tstep));
                int i1 = std::min(h->tnx - 1, (int)std::floor((xs[q + 1] - h->tminx) / h->tstep));
                for (int i = i0; i <= i1; ++i) cover.emplace_back(j * h->tnx + i, (int)k);
            }
        }
    }
    std::sort(cover.begin(), cover.end());

    h->floor1.assign(h->terr.begin(), h->terr.end());
    h->onprism1.assign(n, 0);
    h->kind1.assign(n, 0);
    h->head1.assign(n, std::numeric_limits<float>::infinity());
    std::vector<Slab> bt;
    for (size_t a = 0; a < cover.size();) {
        size_t b = a;
        int cell = cover[a].first;
        bt.clear();
        while (b < cover.size() && cover[b].first == cell) {
            const Prism& p = h->prisms[cover[b].second];
            bt.push_back({p.base, p.top, p.kind});
            ++b;
        }
        uint8_t k;
        double over;
        h->floor1[cell] = (float)apply_floor_rule(h, h->terr[cell], bt, &k, &over);
        h->onprism1[cell] = k != 0;
        h->kind1[cell] = k;
        h->head1[cell] = (float)(over - h->floor1[cell]);
        a = b;
    }

    // wall1: a lattice point that rises above a 4-neighbour by more than you can walk up.
    h->wall1.assign(n, 0);
    for (int j = 0; j < h->tny; ++j) {
        for (int i = 0; i < h->tnx; ++i) {
            size_t c = (size_t)j * h->tnx + i;
            float f = h->floor1[c];
            static const int ox[4] = {1, -1, 0, 0}, oy[4] = {0, 0, 1, -1};
            for (int d = 0; d < 4; ++d) {
                int ii = i + ox[d], jj = j + oy[d];
                if (ii < 0 || jj < 0 || ii >= h->tnx || jj >= h->tny) continue;
                size_t q = (size_t)jj * h->tnx + ii;
                double thr = (h->onprism1[c] || h->onprism1[q]) ? h->step_up : h->slope_tan * h->tstep;
                if (f - h->floor1[q] > thr) { h->wall1[c] = 1; break; }
            }
        }
    }
}

// ---------------------------------------------------------------- C ABI: lifecycle

extern "C" {

MC_API MechCore* mc_create(void) { return new MechCore(); }
MC_API void mc_destroy(MechCore* h) { delete h; }

MC_API int mc_set_terrain(MechCore* h, const int16_t* data, int nx, int ny,
                          double min_x, double min_y, double step, double scale) {
    if (!h || !data || nx < 2 || ny < 2 || step <= 0) return 0;
    h->tnx = nx; h->tny = ny; h->tminx = min_x; h->tminy = min_y; h->tstep = step;
    h->terr.resize((size_t)nx * ny);
    for (size_t k = 0; k < h->terr.size(); ++k) h->terr[k] = (float)(data[k] * scale);
    h->terr_max = *std::max_element(h->terr.begin(), h->terr.end());
    h->cnx = (nx - 1 + 3) / 4;
    h->cny = (ny - 1 + 3) / 4;
    h->cmax.assign((size_t)h->cnx * h->cny, -1e9f);
    for (int bj = 0; bj < h->cny; ++bj)
        for (int bi = 0; bi < h->cnx; ++bi) {
            float m = -1e9f;
            for (int j = 4 * bj; j <= std::min(4 * bj + 4, ny - 1); ++j)
                for (int i = 4 * bi; i <= std::min(4 * bi + 4, nx - 1); ++i) m = std::max(m, h->terr[(size_t)j * nx + i]);
            h->cmax[(size_t)bj * h->cnx + bi] = m;
        }
    h->c16nx = (h->cnx + 3) / 4;
    h->c16ny = (h->cny + 3) / 4;
    h->cmax16.assign((size_t)h->c16nx * h->c16ny, -1e9f);
    for (int bj = 0; bj < h->cny; ++bj)
        for (int bi = 0; bi < h->cnx; ++bi) {
            float& m = h->cmax16[(size_t)(bj / 4) * h->c16nx + bi / 4];
            m = std::max(m, h->cmax[(size_t)bj * h->cnx + bi]);
        }
    return 1;
}

MC_API int mc_add_prism(MechCore* h, int kind, double base, double top,
                        const float* ring, int ring_n,
                        const float* holes, const int* hole_counts, int n_holes) {
    if (!h || !ring || ring_n < 3) return 0;
    Prism p;
    p.kind = kind; p.base = (float)base; p.top = (float)top;
    p.minx = p.miny = std::numeric_limits<float>::infinity();
    p.maxx = p.maxy = -std::numeric_limits<float>::infinity();
    auto add_loop = [&](const float* pts, int n) {
        for (int k = 0; k < n; ++k) {
            const float* a = pts + 2 * k;
            const float* b = pts + 2 * ((k + 1) % n);
            p.edges.insert(p.edges.end(), {a[0], a[1], b[0], b[1]});
            p.minx = std::min(p.minx, a[0]); p.maxx = std::max(p.maxx, a[0]);
            p.miny = std::min(p.miny, a[1]); p.maxy = std::max(p.maxy, a[1]);
        }
    };
    add_loop(ring, ring_n);
    const float* hp = holes;
    for (int k = 0; k < n_holes; ++k) {
        int c = hole_counts[k];
        if (c >= 3) add_loop(hp, c);
        hp += 2 * c;
    }
    h->prisms.push_back(std::move(p));
    return (int)h->prisms.size();
}

MC_API int mc_set_trees(MechCore* h, const float* data, int n) {
    if (!h) return 0;
    h->trees.clear();
    h->trees.reserve(n);
    for (int k = 0; k < n; ++k) {
        const float* d = data + 9 * k;
        Tree t{d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7], d[8], 0, 0, 0, 0, 0, 0};
        t.crown_cz = t.z + 0.5f * (t.crown_base + t.height);
        t.crown_hz = std::max(0.5f, 0.5f * (t.height - t.crown_base));
        float r = std::max(t.crown_r, t.trunk_r);
        t.minx = std::min(t.x - t.trunk_r, t.cx - r); t.maxx = std::max(t.x + t.trunk_r, t.cx + r);
        t.miny = std::min(t.y - t.trunk_r, t.cy - r); t.maxy = std::max(t.y + t.trunk_r, t.cy + r);
        h->trees.push_back(t);
    }
    return (int)h->trees.size();
}

MC_API int mc_build(MechCore* h, const double* params, int n_params) {
    if (!h || h->terr.empty()) return 0;
    auto t0 = std::chrono::steady_clock::now();
    if (params) {
        if (n_params > MC_P_STEP_UP) h->step_up = params[MC_P_STEP_UP];
        if (n_params > MC_P_MAX_SLOPE_DEG) h->max_slope_deg = params[MC_P_MAX_SLOPE_DEG];
        if (n_params > MC_P_MECH_HEIGHT) h->mech_h = params[MC_P_MECH_HEIGHT];
        if (n_params > MC_P_MECH_RADIUS) h->mech_r = params[MC_P_MECH_RADIUS];
        if (n_params > MC_P_CANOPY_DENSITY) h->canopy_density = params[MC_P_CANOPY_DENSITY];
        if (n_params > MC_P_CANOPY_BLOCK_T) h->canopy_block_t = params[MC_P_CANOPY_BLOCK_T];
    }
    h->slope_tan = std::tan(h->max_slope_deg * MC_PI / 180.0);
    build_buckets(h);
    build_floor(h);
    build_nav(h);
    h->built = true;
    h->build_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    return 1;
}

MC_API double mc_build_ms(MechCore* h) { return h ? h->build_ms : 0.0; }

MC_API void mc_grid_info(MechCore* h, int* out_i, double* out_d) {
    if (out_i) { out_i[0] = h->nnx; out_i[1] = h->nny; }
    if (out_d) { out_d[0] = h->tminx; out_d[1] = h->tminy; out_d[2] = h->tstep * 2; }
}

MC_API int mc_get_layer(MechCore* h, int layer, float* out, int n) {
    if (!h->built) return 0;
    int total = h->nnx * h->nny;
    if (!out || n < total) return 0;
    for (int c = 0; c < total; ++c) {
        float v = 0;
        switch (layer) {
            case MC_L_FLOOR: v = h->nfloor[c]; break;
            case MC_L_CLEARANCE: v = h->nclear[c] * 0.25f; break;
            case MC_L_COMPONENT: v = (float)h->ncomp[c]; break;
            case MC_L_GROUND: v = (h->ground_comp >= 0 && h->ncomp[c] == h->ground_comp) ? 1.f : 0.f; break;
            case MC_L_COVER: v = h->ncover[c] / 16.f; break;
            case MC_L_EDGES: { int b = h->nedges[c], k = 0; while (b) { k += b & 1; b >>= 1; } v = (float)k; break; }
            case MC_L_KIND: v = h->nkind[c]; break;
            default: return 0;
        }
        out[c] = v;
    }
    return total;
}

// ---------------------------------------------------------------- C ABI: point queries

MC_API double mc_ground_z(MechCore* h, double x, double y) { return terrain_z(h, x, y); }

MC_API double mc_floor_z(MechCore* h, double x, double y) { return floor_at(h, x, y, nullptr, nullptr); }

MC_API double mc_clearance(MechCore* h, double x, double y) {
    int i, j;
    if (!h->built || !nav_cell(h, x, y, &i, &j)) return 0.0;
    return h->nclear[(size_t)j * h->nnx + i] * 0.25;
}

MC_API double mc_cover(MechCore* h, double x, double y) {
    int i, j;
    if (!h->built || !nav_cell(h, x, y, &i, &j)) return 0.0;
    return h->ncover[(size_t)j * h->nnx + i] / 16.0;
}

MC_API int mc_component(MechCore* h, double x, double y) {
    int i, j;
    if (!h->built || !nav_cell(h, x, y, &i, &j)) return -1;
    return h->ncomp[(size_t)j * h->nnx + i];
}

MC_API int mc_is_ground(MechCore* h, double x, double y) {
    int c = mc_component(h, x, y);
    return c >= 0 && c == h->ground_comp;
}

}  // extern "C"
