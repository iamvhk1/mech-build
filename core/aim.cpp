// Ballistics: gun lead, mortar pitch, shell impact prediction.
#include <algorithm>
#include <cmath>

#include "internal.h"

extern "C" {

MC_API int mc_gun_lead(double mx, double my, double mz, double tx, double ty, double tz,
                       double vx, double vy, double vz, double speed, double offset, double* out) {
    if (speed <= 0) return 0;
    double t = 0, px = tx, py = ty, pz = tz;
    for (int it = 0; it < 6; ++it) {
        px = tx + vx * t; py = ty + vy * t; pz = tz + vz * t;
        double dx = px - mx, dy = py - my, dz = pz - mz;
        double d = std::sqrt(dx * dx + dy * dy + dz * dz);
        t = std::max(0.0, d - offset) / speed;
    }
    double dx = px - mx, dy = py - my, dz = pz - mz;
    out[0] = std::atan2(dy, dx);
    out[1] = std::atan2(dz, std::sqrt(dx * dx + dy * dy));
    out[2] = t;
    return 1;
}

// Pitch so a shell launched at `speed` from (muzzle + offset along aim) lands on the target.
MC_API int mc_mortar_pitch(double mx, double my, double mz, double tx, double ty, double tz,
                           double speed, double gravity, double offset, int prefer_high,
                           double min_pitch, double max_pitch, double* out) {
    if (speed <= 0 || gravity <= 0) return 0;
    double yaw = std::atan2(ty - my, tx - mx);
    double cy = std::cos(yaw), sy = std::sin(yaw);
    double pitch = 0.6, flight = 0;
    bool ok = false;
    for (int it = 0; it < 4; ++it) {
        double cp = std::cos(pitch), sp = std::sin(pitch);
        double ox = mx + offset * cp * cy, oy = my + offset * cp * sy, oz = mz + offset * sp;
        if (it == 0) { ox = mx; oy = my; oz = mz; }
        double d = std::hypot(tx - ox, ty - oy), dz = tz - oz;
        if (d < 1e-3) return 0;
        double v2 = speed * speed;
        double disc = v2 * v2 - gravity * (gravity * d * d + 2 * dz * v2);
        if (disc < 0) { ok = false; break; }
        double sq = std::sqrt(disc);
        double th = std::atan((v2 + (prefer_high ? sq : -sq)) / (gravity * d));
        pitch = th;
        flight = d / (speed * std::cos(th));
        ok = true;
    }
    if (!ok || pitch < min_pitch || pitch > max_pitch) return 0;
    out[0] = yaw;
    out[1] = pitch;
    out[2] = flight;
    return 1;
}

MC_API int mc_shell_impact(MechCore* h, double px, double py, double pz,
                           double vx, double vy, double vz, double gravity, double max_t, double* out) {
    const double dt = 0.05;
    double t = 0;
    while (t < max_t) {
        double nx = px + vx * dt, ny = py + vy * dt, nvz = vz - gravity * dt;
        double nz = pz + (vz + nvz) * 0.5 * dt;
        double f = shot_ray(h, px, py, pz, nx, ny, nz);
        if (f < 1.0) {
            out[0] = px + (nx - px) * f; out[1] = py + (ny - py) * f; out[2] = pz + (nz - pz) * f;
            out[3] = t + f * dt;
            return 1;
        }
        // shot_ray samples terrain inside the segment only; also check the end point
        if (nz <= terrain_z(h, nx, ny)) {
            out[0] = nx; out[1] = ny; out[2] = nz; out[3] = t + dt;
            return 1;
        }
        px = nx; py = ny; pz = nz; vz = nvz; t += dt;
    }
    return 0;
}

}  // extern "C"
