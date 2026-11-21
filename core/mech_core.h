/* mech_core: geometry engine for the mechfight/1 bot.
 *
 * C ABI only: opaque handle, POD arguments, caller-owned output buffers.
 * Python parses world.json and passes flat arrays (see core_api.py).
 * Coordinates: x east, y north, z up, meters. Yaw from +x counter-clockwise.
 */
#ifndef MECH_CORE_H
#define MECH_CORE_H

#include <stdint.h>

#if defined(_WIN32)
#define MC_API __declspec(dllexport)
#else
#define MC_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct MechCore MechCore;

/* Build parameters, indices into the `params` array of mc_build. */
enum {
    MC_P_STEP_UP = 0,       /* mech.step_up (1.2) */
    MC_P_MAX_SLOPE_DEG,     /* mech.max_slope_deg (50) */
    MC_P_MECH_HEIGHT,       /* mech.height (9) */
    MC_P_MECH_RADIUS,       /* mech.radius (2.5) */
    MC_P_CANOPY_DENSITY,    /* world.rules.canopyDensity (0.35) */
    MC_P_CANOPY_BLOCK_T,    /* world.rules.canopyBlockT (0.25) */
    MC_P_COUNT
};

/* Layers for mc_get_layer (nav grid, nnx * nny floats, row-major, row = y). */
enum {
    MC_L_FLOOR = 0,         /* floor height (m) */
    MC_L_CLEARANCE,         /* distance to nearest wall (m, capped) */
    MC_L_COMPONENT,         /* connected component id (-1 none) */
    MC_L_GROUND,            /* 1 if in the ground (street) component */
    MC_L_COVER,             /* static cover 0..1 */
    MC_L_EDGES,             /* number of outgoing walkable edges 0..8 */
    MC_L_KIND,              /* floor kind: 0 terrain, 1 building roof, 2 stadium, 3 bridge */
    MC_L_COUNT
};

MC_API MechCore* mc_create(void);
MC_API void mc_destroy(MechCore* h);

/* Map ingestion. Call set_terrain, add_prism (repeatedly), set_trees, then mc_build. */
MC_API int mc_set_terrain(MechCore* h, const int16_t* data, int nx, int ny,
                          double min_x, double min_y, double step, double scale);
/* ring: ring_n points (2*ring_n floats). holes: all hole points concatenated,
 * hole_counts[i] = points in hole i. kind: 0 building, 1 stadium, 2 bridge. */
MC_API int mc_add_prism(MechCore* h, int kind, double base, double top,
                        const float* ring, int ring_n,
                        const float* holes, const int* hole_counts, int n_holes);
/* 9 floats per tree: x y z height crownR crownBase trunkR crownX crownY */
MC_API int mc_set_trees(MechCore* h, const float* data, int n);
MC_API int mc_build(MechCore* h, const double* params, int n_params);
MC_API double mc_build_ms(MechCore* h);

/* Grid info: out_i = {nnx, nny}, out_d = {min_x, min_y, res}. */
MC_API void mc_grid_info(MechCore* h, int* out_i, double* out_d);
MC_API int mc_get_layer(MechCore* h, int layer, float* out, int n);

/* Point queries. */
MC_API double mc_ground_z(MechCore* h, double x, double y);
MC_API double mc_floor_z(MechCore* h, double x, double y);   /* standing height, ground layer */
MC_API double mc_clearance(MechCore* h, double x, double y); /* nav-cell clearance (m) */
MC_API double mc_cover(MechCore* h, double x, double y);     /* 0..1 */
MC_API int mc_component(MechCore* h, double x, double y);
MC_API int mc_is_ground(MechCore* h, double x, double y);

/* Line of sight. shot_los: buildings/bridges/terrain; returns hit fraction in [0,1], 1 = clear.
 * vision_los: shot_los + tree trunks + canopy; returns 1 visible, 0 blocked. */
MC_API double mc_shot_los(MechCore* h, double ax, double ay, double az, double bx, double by, double bz);
MC_API int mc_vision_los(MechCore* h, double ax, double ay, double az, double bx, double by, double bz);
/* segs: n * 6 doubles (ax ay az bx by bz). */
MC_API void mc_shot_los_batch(MechCore* h, int n, const double* segs, double* out);
MC_API void mc_vision_los_batch(MechCore* h, int n, const double* segs, uint8_t* out);
/* Protocol §8 vision rules. eye_z = observer eye height (absolute). Returns 1 if seen. */
MC_API int mc_can_see(MechCore* h, double ox, double oy, double eye_z, double aim_yaw,
                      double tx, double ty, double t_center_z, double t_top_z,
                      double near_range, double range, double fov_deg);

/* Navigation. */
MC_API int mc_nearest_walkable(MechCore* h, double x, double y, double radius, int ground_only,
                               double* out_xy);
/* height: mech height for headroom under bridges (<= 0: base mech height). */
MC_API int mc_segment_walkable(MechCore* h, double ax, double ay, double bx, double by, double radius,
                               double height);
/* height: mech height (<= 0: base). max_jump_rise: allow steps up to this many meters as jumps
 * (0 = walk only). allow_roofs: jumps may land on building roofs (otherwise never). threats: n * 4 doubles (x, y, range, weight).
 * zone: 4 doubles (cx, cy, r, penalty) or NULL.
 * h_weight >= 1 inflates the heuristic (1 = optimal, 1.3 = much faster, slightly longer paths).
 * Writes waypoints (excluding start, including snapped goal) to out_xyj, 3 doubles each:
 * x, y, kind (0 = walk, 1 = jump needed to reach it, 2 = drop off a ledge to reach it).
 * Returns number of waypoints, or <0 on failure (-1 no start, -2 no goal, -3 no path). */
MC_API int mc_find_path(MechCore* h, double sx, double sy, double gx, double gy, double radius,
                        double height, double max_jump_rise, int allow_roofs,
                        const double* threats, int n_threats, const double* zone,
                        double cover_weight, double h_weight, int max_expansions,
                        double* out_xyj, int max_pts);

/* 16-direction local steering. zone: 3 doubles (cx, cy, r) or NULL. shells: n * 4 doubles
 * (x, y, splash_radius, seconds_to_impact). weights: 4 doubles (align, clear, zone, shell) or NULL.
 * speed: our current move speed (m/s). out: 3 doubles (dx, dy, score). Returns best index. */
MC_API int mc_steer(MechCore* h, double px, double py, double wx, double wy, double radius,
                    double speed, const double* zone, const double* shells, int n_shells,
                    const double* weights, double* out);

/* Ballistics (no handle needed). offset: distance the shot spawns out along the aim (radius + 0.5).
 * out: 3 doubles (yaw, pitch, flight_time). Return 1 on success. */
MC_API int mc_gun_lead(double mx, double my, double mz, double tx, double ty, double tz,
                       double vx, double vy, double vz, double speed, double offset, double* out);
MC_API int mc_mortar_pitch(double mx, double my, double mz, double tx, double ty, double tz,
                           double speed, double gravity, double offset, int prefer_high,
                           double min_pitch, double max_pitch, double* out);
/* Predict where a falling shell hits geometry. out: 4 doubles (x, y, z, t). */
MC_API int mc_shell_impact(MechCore* h, double px, double py, double pz,
                           double vx, double vy, double vz, double gravity, double max_t, double* out);

#ifdef __cplusplus
}
#endif

#endif
