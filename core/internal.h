// Internal shared definitions for mech_core (not part of the C ABI).
#pragma once

#include <cmath>
#include <cstdint>
#include <vector>

#include "mech_core.h"

struct Prism {
    int kind = 0;
    float base = 0, top = 0;
    float minx = 0, miny = 0, maxx = 0, maxy = 0;
    // All edges (ring + holes) as x0,y0,x1,y1. Even-odd over all edges = ring minus holes.
    std::vector<float> edges;
};

struct Tree {
    float x, y, z, height, crown_r, crown_base, trunk_r, cx, cy;
    // derived
    float crown_cz, crown_hz;  // ellipsoid centre z and vertical half-axis
    float minx, miny, maxx, maxy;
};

struct MechCore {
    // terrain (vertex grid, meters)
    int tnx = 0, tny = 0;
    double tminx = 0, tminy = 0, tstep = 1;
    std::vector<float> terr;
    float terr_max = 0;
    // coarse terrain maxima, 4x4 lattice blocks (vertices on block borders included)
    int cnx = 0, cny = 0;
    std::vector<float> cmax;
    int c16nx = 0, c16ny = 0;       // 16x16 lattice blocks
    std::vector<float> cmax16;

    std::vector<Prism> prisms;
    std::vector<Tree> trees;

    // params
    double step_up = 1.2, max_slope_deg = 50, mech_h = 9, mech_r = 2.5;
    double canopy_density = 0.35, canopy_block_t = 0.25;
    double slope_tan = 1.19;

    // broad-phase buckets (shared by prisms and trees)
    double bminx = 0, bminy = 0, bcell = 16;
    int bnx = 0, bny = 0;
    std::vector<std::vector<int>> pbuckets, tbuckets;
    std::vector<uint32_t> pstamp, tstamp;
    uint32_t stamp = 0;

    // floor model on the terrain lattice (1 m)
    std::vector<float> floor1;      // standing height, ground layer
    std::vector<uint8_t> onprism1;  // floor comes from a prism top
    std::vector<uint8_t> wall1;     // higher than a neighbour beyond step/slope

    // nav grid (2 m), cell (i, j) <-> lattice (2i, 2j)
    int nnx = 0, nny = 0;
    double nres = 2;
    std::vector<float> nfloor;
    std::vector<uint8_t> nclear;   // clearance in 0.25 m units
    std::vector<uint8_t> nedges;   // bit d: move toward DIR[d] allowed (height rules only)
    std::vector<uint8_t> ncover;   // 0..16
    std::vector<int> ncomp;
    int ground_comp = -1;

    // A* scratch
    std::vector<float> g;
    std::vector<int> parent;
    std::vector<uint32_t> gen, closed_gen;
    uint32_t cur_gen = 0;
    int tcnx = 0, tcny = 0;            // threat-cache blocks (4x4 nav cells)
    std::vector<float> threat_cache;   // per block, per threat slot: 1 visible, 0 hidden
    std::vector<uint32_t> threat_gen;

    double build_ms = 0;
    bool built = false;
};

static const double MC_PI = 3.14159265358979323846;

// 8 neighbour directions: E, NE, N, NW, W, SW, S, SE
static const int DIR_DX[8] = {1, 1, 0, -1, -1, -1, 0, 1};
static const int DIR_DY[8] = {0, 1, 1, 1, 0, -1, -1, -1};

// map.cpp
double terrain_z(const MechCore* h, double x, double y);
bool point_in_prism2d(const Prism& p, double x, double y);
double floor_at(const MechCore* h, double x, double y, bool* on_prism, double* overhead);
void build_buckets(MechCore* h);
inline int bucket_of(const MechCore* h, double x, double y, int* bi, int* bj) {
    int i = (int)std::floor((x - h->bminx) / h->bcell);
    int j = (int)std::floor((y - h->bminy) / h->bcell);
    *bi = i; *bj = j;
    return (i >= 0 && j >= 0 && i < h->bnx && j < h->bny) ? j * h->bnx + i : -1;
}

inline double coarse_max(const MechCore* h, double x, double y) {
    int i = (int)std::floor((x - h->tminx) / (h->tstep * 4));
    int j = (int)std::floor((y - h->tminy) / (h->tstep * 4));
    i = i < 0 ? 0 : (i >= h->cnx ? h->cnx - 1 : i);
    j = j < 0 ? 0 : (j >= h->cny ? h->cny - 1 : j);
    return h->cmax[(size_t)j * h->cnx + i];
}

inline double coarse_max16(const MechCore* h, double x, double y) {
    int i = (int)std::floor((x - h->tminx) / (h->tstep * 16));
    int j = (int)std::floor((y - h->tminy) / (h->tstep * 16));
    i = i < 0 ? 0 : (i >= h->c16nx ? h->c16nx - 1 : i);
    j = j < 0 ? 0 : (j >= h->c16ny ? h->c16ny - 1 : j);
    return h->cmax16[(size_t)j * h->c16nx + i];
}

// los.cpp
double shot_ray(MechCore* h, double ax, double ay, double az, double bx, double by, double bz);
bool vision_ray(MechCore* h, double ax, double ay, double az, double bx, double by, double bz);

// nav.cpp
void build_nav(MechCore* h);
inline bool nav_cell(const MechCore* h, double x, double y, int* ci, int* cj) {
    int i = (int)std::lround((x - h->tminx) / (h->tstep * 2));
    int j = (int)std::lround((y - h->tminy) / (h->tstep * 2));
    *ci = i; *cj = j;
    return i >= 0 && j >= 0 && i < h->nnx && j < h->nny;
}
inline double nav_x(const MechCore* h, int i) { return h->tminx + i * h->tstep * 2; }
inline double nav_y(const MechCore* h, int j) { return h->tminy + j * h->tstep * 2; }
