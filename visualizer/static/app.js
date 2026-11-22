/**
 * Mech Royale - 2D Strategy Visualizer Engine
 */

(function () {
  'use strict';

  // --- Constants & Arena Metadata ---
  const ARENA = {
    min_x: -513.0,
    min_y: -334.0,
    max_x: 557.0,
    max_y: 390.0,
    width_m: 1070.0,
    height_m: 724.0,
  };

  // --- State ---
  let canvas, ctx;
  let mapImage = new Image();
  let mapLoaded = false;

  let currentReplay = null;
  let currentFrameIdx = 0;
  let isPlaying = false;
  let playSpeed = 1.0;
  let lastAnimTime = 0;
  let frameAccumulator = 0;

  // Camera
  let camX = 0;
  let camY = 0;
  let scale = 1.5; // pixels per world meter
  let isDragging = false;
  let dragStartX = 0, dragStartY = 0;
  let followBot = true;

  // Overlays config
  const layers = {
    map: true,
    zone: true,
    path: true,
    engage: true,
    lightning: true,
    safe: false,
    hunters: true,
    drops: true,
    economy: true,
  };

  // Mouse inspection
  let mouseWorld = { x: 0, y: 0 };
  let hoveredEntity = null;

  // --- Initialization ---
  window.addEventListener('DOMContentLoaded', async () => {
    canvas = document.getElementById('gameCanvas');
    ctx = canvas.getContext('2d');

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    setupControls();
    setupLayerToggles();
    setupCanvasInteractions();

    // Load Map Image
    mapImage.src = 'map.png';
    mapImage.onload = () => {
      mapLoaded = true;
      requestRedraw();
    };

    // Load available replays
    await loadReplayList();

    // Start render loop
    requestAnimationFrame(renderLoop);
  });

  function resizeCanvas() {
    const container = document.getElementById('viewportContainer');
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
    if (scale <= 1.0) resetCameraView();
  }

  function resetCameraView() {
    camX = (ARENA.min_x + ARENA.max_x) / 2;
    camY = (ARENA.min_y + ARENA.max_y) / 2;
    scale = Math.min(canvas.width / ARENA.width_m, canvas.height / ARENA.height_m) * 0.95;
    followBot = false;
    updateFollowBtn();
  }

  // --- Coordinate Transformations ---
  function worldToScreen(wx, wy) {
    return {
      x: (wx - camX) * scale + canvas.width / 2,
      y: (camY - wy) * scale + canvas.height / 2,
    };
  }

  function screenToWorld(sx, sy) {
    return {
      x: camX + (sx - canvas.width / 2) / scale,
      y: camY - (sy - canvas.height / 2) / scale,
    };
  }

  // --- API & Replay Loading ---
  async function loadReplayList() {
    try {
      const res = await fetch('/api/replays');
      const list = await res.json();
      const select = document.getElementById('replaySelect');
      select.innerHTML = '';

      list.forEach((r) => {
        const opt = document.createElement('option');
        opt.value = r.id;
        opt.textContent = `${r.title} (${r.frames_count} frames)`;
        select.appendChild(opt);
      });

      if (list.length > 0) {
        select.value = list[0].id;
        await loadReplay(list[0].id);
      }
    } catch (e) {
      console.error('Failed to load replays:', e);
    }
  }

  async function loadReplay(id) {
    pause();
    try {
      const res = await fetch(`/api/replay?id=${encodeURIComponent(id)}`);
      currentReplay = await res.json();
      currentFrameIdx = 0;

      // Update UI Meta
      document.getElementById('presetPill').textContent = `PRESET: ${currentReplay.preset || 'BEST'}`.toUpperCase();
      document.getElementById('timeTotal').textContent = formatTime(currentReplay.total_time || 0);

      const slider = document.getElementById('timelineSlider');
      slider.min = 0;
      slider.max = (currentReplay.frames || []).length - 1;
      slider.value = 0;

      renderTimelineEvents();

      // Lock on bot start position
      if (currentReplay.frames && currentReplay.frames.length > 0) {
        const first = currentReplay.frames[0];
        camX = first.self.pos[0];
        camY = first.self.pos[1];
        scale = 2.2;
        followBot = true;
        updateFollowBtn();
      }

      updateHUD();
      requestRedraw();
    } catch (e) {
      console.error('Failed to load replay content:', e);
    }
  }

  function renderTimelineEvents() {
    const container = document.getElementById('timelineEvents');
    container.innerHTML = '';
    if (!currentReplay || !currentReplay.events || !currentReplay.total_time) return;

    const totalT = currentReplay.total_time;
    currentReplay.events.forEach((ev) => {
      const marker = document.createElement('div');
      marker.className = `event-marker event-${ev.type}`;
      marker.style.left = `${(ev.t / totalT) * 100}%`;
      marker.title = `${ev.desc} (${ev.t.toFixed(1)}s)`;
      marker.addEventListener('click', () => {
        seekToTime(ev.t);
      });
      container.appendChild(marker);
    });
  }

  function seekToTime(targetT) {
    if (!currentReplay || !currentReplay.frames) return;
    let closest = 0, minDiff = 1e9;
    currentReplay.frames.forEach((f, idx) => {
      const diff = Math.abs(f.t - targetT);
      if (diff < minDiff) {
        minDiff = diff;
        closest = idx;
      }
    });
    seekToFrame(closest);
  }

  function seekToFrame(idx) {
    if (!currentReplay || !currentReplay.frames) return;
    currentFrameIdx = Math.max(0, Math.min(idx, currentReplay.frames.length - 1));
    document.getElementById('timelineSlider').value = currentFrameIdx;
    updateHUD();
  }

  // --- Playback Engine ---
  function play() {
    isPlaying = true;
    document.getElementById('btnPlayPause').textContent = '⏸';
    lastAnimTime = performance.now();
  }

  function pause() {
    isPlaying = false;
    document.getElementById('btnPlayPause').textContent = '▶';
  }

  function togglePlay() {
    if (isPlaying) pause();
    else play();
  }

  function renderLoop(time) {
    if (isPlaying && currentReplay && currentReplay.frames) {
      const dt = (time - lastAnimTime) / 1000;
      lastAnimTime = time;

      // Frame interval is typically 0.1s (10 Hz)
      const currentFrame = currentReplay.frames[currentFrameIdx];
      const nextFrame = currentReplay.frames[currentFrameIdx + 1];
      const frameDT = nextFrame ? (nextFrame.t - currentFrame.t) : 0.1;

      frameAccumulator += dt * playSpeed;
      while (frameAccumulator >= frameDT) {
        frameAccumulator -= frameDT;
        if (currentFrameIdx < currentReplay.frames.length - 1) {
          currentFrameIdx++;
        } else {
          pause();
          break;
        }
      }
      document.getElementById('timelineSlider').value = currentFrameIdx;
      updateHUD();
    } else {
      lastAnimTime = time;
    }

    drawScene();
    requestAnimationFrame(renderLoop);
  }

  function requestRedraw() {
    drawScene();
  }

  // --- Canvas Rendering ---
  function drawScene() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!currentReplay || !currentReplay.frames || currentReplay.frames.length === 0) {
      drawEmptyState();
      return;
    }

    const frame = currentReplay.frames[currentFrameIdx];
    if (!frame) return;

    // Follow Bot camera
    if (followBot && frame.self) {
      camX += (frame.self.pos[0] - camX) * 0.1;
      camY += (frame.self.pos[1] - camY) * 0.1;
    }

    // 1. Campus Map Layer
    if (layers.map && mapLoaded) {
      const p1 = worldToScreen(ARENA.min_x, ARENA.max_y);
      const p2 = worldToScreen(ARENA.max_x, ARENA.min_y);
      ctx.drawImage(mapImage, p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);
    } else {
      ctx.fillStyle = '#10141d';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }

    // 2. Zone Circles Layer
    if (layers.zone && frame.zone) {
      drawZone(frame.zone);
    }

    // 3. Economy: Crates, Cubes & Pickups
    if (layers.economy) {
      drawEconomy(frame);
    }

    // 4. Supply Drops
    if (layers.drops && frame.drops) {
      drawDrops(frame.drops);
    }

    // 5. Enemy Hunters
    if (frame.mechs) {
      drawHunters(frame.mechs, frame.self);
    }

    // 6. Our Hero Mech
    if (frame.self) {
      drawHeroMech(frame.self);
    }

    // 7. Beams & Projectiles
    if (frame.beams) {
      drawBeams(frame.beams);
    }

    // 8. Hover Highlight & Tooltip
    drawHoverInspection();
  }

  function drawZone(zone) {
    const cur = worldToScreen(zone.center[0], zone.center[1]);
    const curR = zone.radius * scale;

    // Outer storm danger tint
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, canvas.width, canvas.height);
    ctx.arc(cur.x, cur.y, Math.max(0, curR), 0, Math.PI * 2, true);
    ctx.fillStyle = 'rgba(239, 68, 68, 0.12)';
    ctx.fill();

    // Current zone ring
    ctx.beginPath();
    ctx.arc(cur.x, cur.y, Math.max(0, curR), 0, Math.PI * 2);
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = '#38bdf8';
    ctx.shadowColor = '#38bdf8';
    ctx.shadowBlur = 8;
    ctx.stroke();
    ctx.restore();

    // Next zone circle (dashed amber)
    if (zone.next_radius && zone.next_radius > 0) {
      const nxt = worldToScreen(zone.next_center[0], zone.next_center[1]);
      const nxtR = zone.next_radius * scale;

      ctx.save();
      ctx.beginPath();
      ctx.arc(nxt.x, nxt.y, Math.max(0, nxtR), 0, Math.PI * 2);
      ctx.setLineDash([8, 6]);
      ctx.lineWidth = 2;
      ctx.strokeStyle = '#f59e0b';
      ctx.stroke();

      // Next center mark
      ctx.beginPath();
      ctx.arc(nxt.x, nxt.y, 4, 0, Math.PI * 2);
      ctx.fillStyle = '#f59e0b';
      ctx.fill();
      ctx.restore();
    }
  }

  function drawEconomy(frame) {
    // Floor Cubes (Glowing Purple Diamond)
    (frame.cubes || []).forEach((c) => {
      const s = worldToScreen(c.pos[0], c.pos[1]);
      ctx.save();
      ctx.translate(s.x, s.y);
      ctx.rotate(Math.PI / 4);
      ctx.fillStyle = '#c084fc';
      ctx.shadowColor = '#c084fc';
      ctx.shadowBlur = 6;
      ctx.fillRect(-4, -4, 8, 8);
      ctx.restore();
    });

    // Weapon Pickups
    (frame.pickups || []).forEach((p) => {
      const s = worldToScreen(p.pos[0], p.pos[1]);
      ctx.save();
      ctx.beginPath();
      ctx.arc(s.x, s.y, 6, 0, Math.PI * 2);

      let col = '#38bdf8';
      let icon = 'W';
      if (p.kind === 'lightning') { col = '#facc15'; icon = '⚡'; }
      else if (p.kind === 'laser') { col = '#38bdf8'; icon = '⌖'; }
      else if (p.kind === 'mortar') { col = '#fb923c'; icon = '☄'; }

      ctx.fillStyle = 'rgba(15, 23, 42, 0.8)';
      ctx.fill();
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = col;
      ctx.stroke();

      ctx.fillStyle = col;
      ctx.font = '9px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(icon, s.x, s.y);
      ctx.restore();
    });
  }

  function drawDrops(drops) {
    drops.forEach((d) => {
      const s = worldToScreen(d.pos[0], d.pos[1]);
      const rScreen = 8.0 * scale;

      ctx.save();
      // 8m capture ring
      ctx.beginPath();
      ctx.arc(s.x, s.y, rScreen, 0, Math.PI * 2);
      ctx.setLineDash([6, 4]);
      ctx.lineWidth = 2;
      ctx.strokeStyle = '#c084fc';
      ctx.stroke();

      // Progress fill arc
      if (d.progress > 0) {
        ctx.beginPath();
        const startA = -Math.PI / 2;
        const endA = startA + (d.progress / 4.0) * Math.PI * 2;
        ctx.arc(s.x, s.y, rScreen, startA, endA);
        ctx.setLineDash([]);
        ctx.lineWidth = 4;
        ctx.strokeStyle = '#10b981';
        ctx.stroke();
      }

      // Drop icon box
      ctx.beginPath();
      ctx.arc(s.x, s.y, 8, 0, Math.PI * 2);
      ctx.fillStyle = d.lands_in > 0 ? '#64748b' : '#c084fc';
      ctx.fill();

      // Text label
      ctx.font = '10px monospace';
      ctx.fillStyle = '#fff';
      ctx.textAlign = 'center';
      const label = d.lands_in > 0 ? `DROP (${d.lands_in.toFixed(0)}s)` : `DROP (${d.progress.toFixed(1)}s/4s)`;
      ctx.fillText(label, s.x, s.y - 12);
      ctx.restore();
    });
  }

  function drawHunters(mechs, hero) {
    mechs.forEach((h) => {
      const s = worldToScreen(h.pos[0], h.pos[1]);
      const r = (h.tier === 'expert' ? 3.2 : 2.5) * scale;

      ctx.save();
      // Hunter sightline / Aim ray
      if (layers.hunters && h.active && h.alive) {
        const aimAngle = h.aim ? h.aim[0] : 0;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(s.x + Math.cos(aimAngle) * 70 * scale, s.y - Math.sin(aimAngle) * 70 * scale);
        ctx.setLineDash([4, 4]);
        ctx.lineWidth = 1;
        ctx.strokeStyle = 'rgba(239, 68, 68, 0.4)';
        ctx.stroke();
      }

      // Tier color
      let col = '#22c55e'; // easy
      if (h.tier === 'medium') col = '#eab308';
      else if (h.tier === 'hard') col = '#f97316';
      else if (h.tier === 'expert') col = '#ef4444';

      // Hunter body circle
      ctx.beginPath();
      ctx.arc(s.x, s.y, Math.max(3, r), 0, Math.PI * 2);
      ctx.fillStyle = col;
      ctx.fill();
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = '#fff';
      ctx.stroke();

      // Active alert ring
      if (h.active) {
        ctx.beginPath();
        ctx.arc(s.x, s.y, Math.max(5, r + 4), 0, Math.PI * 2);
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = '#ef4444';
        ctx.stroke();
      }

      // Health bar above hunter
      if (h.max_hp > 0) {
        const barW = 24;
        const barH = 3;
        const frac = Math.max(0, Math.min(1, h.hp / h.max_hp));
        ctx.fillStyle = 'rgba(0,0,0,0.6)';
        ctx.fillRect(s.x - barW / 2, s.y - r - 8, barW, barH);
        ctx.fillStyle = col;
        ctx.fillRect(s.x - barW / 2, s.y - r - 8, barW * frac, barH);
      }

      // Label
      ctx.font = '9px monospace';
      ctx.fillStyle = '#e2e8f0';
      ctx.textAlign = 'center';
      ctx.fillText(`H${h.id}`, s.x, s.y + r + 10);
      ctx.restore();
    });
  }

  function drawHeroMech(hero) {
    const s = worldToScreen(hero.pos[0], hero.pos[1]);
    const mechR = 2.5 * scale;

    ctx.save();

    // 1. Planned A* Path & Goal Waypoint
    if (layers.path && hero.path && hero.path.length > 0) {
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      hero.path.forEach((p) => {
        const wp = worldToScreen(p[0], p[1]);
        ctx.lineTo(wp.x, wp.y);
      });
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = '#f59e0b';
      ctx.setLineDash([4, 3]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Waypoint dots
      hero.path.forEach((p) => {
        const wp = worldToScreen(p[0], p[1]);
        ctx.beginPath();
        ctx.arc(wp.x, wp.y, 2.5, 0, Math.PI * 2);
        ctx.fillStyle = '#f59e0b';
        ctx.fill();
      });

      // Goal diamond
      if (hero.goal) {
        const g = worldToScreen(hero.goal[0], hero.goal[1]);
        ctx.save();
        ctx.translate(g.x, g.y);
        ctx.rotate(Math.PI / 4);
        ctx.fillStyle = '#38bdf8';
        ctx.fillRect(-5, -5, 10, 10);
        ctx.restore();
      }
    }

    // 2. 60m Engagement Circle
    if (layers.engage) {
      ctx.beginPath();
      ctx.arc(s.x, s.y, 60.0 * scale, 0, Math.PI * 2);
      ctx.setLineDash([6, 6]);
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 3. 45m Lightning Cone (30 deg frontal arc)
    if (layers.lightning) {
      const aimYaw = hero.aim ? hero.aim[0] : 0;
      const coneHalf = (15 * Math.PI) / 180;
      const coneR = 45.0 * scale;

      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      // canvas arc inverts y
      ctx.arc(s.x, s.y, coneR, -aimYaw - coneHalf, -aimYaw + coneHalf);
      ctx.closePath();
      ctx.fillStyle = 'rgba(250, 204, 21, 0.08)';
      ctx.fill();
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(250, 204, 21, 0.35)';
      ctx.stroke();
    }

    // 4. 80m Drop Safe Radius
    if (layers.safe) {
      ctx.beginPath();
      ctx.arc(s.x, s.y, 80.0 * scale, 0, Math.PI * 2);
      ctx.setLineDash([4, 6]);
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.2)';
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 5. Hero Mech Body Circle
    ctx.beginPath();
    ctx.arc(s.x, s.y, Math.max(4, mechR), 0, Math.PI * 2);
    ctx.fillStyle = '#2563eb';
    ctx.shadowColor = '#3b82f6';
    ctx.shadowBlur = 10;
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#60a5fa';
    ctx.stroke();

    // Aim heading line
    if (hero.aim) {
      const yaw = hero.aim[0];
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(s.x + Math.cos(yaw) * 35, s.y - Math.sin(yaw) * 35);
      ctx.lineWidth = 2;
      ctx.strokeStyle = '#ef4444';
      ctx.stroke();
    }

    // Status Banner floating above hero
    ctx.font = 'bold 10px monospace';
    ctx.fillStyle = '#38bdf8';
    ctx.textAlign = 'center';
    const stateText = (hero.pacing_mode || hero.state || 'ROTATE').toUpperCase();
    ctx.fillText(stateText, s.x, s.y - mechR - 12);

    // HP Bar above hero
    const barW = 32;
    const barH = 4;
    const hpFrac = Math.max(0, Math.min(1, hero.hp / (hero.max_hp || 1000)));
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(s.x - barW / 2, s.y - mechR - 7, barW, barH);
    ctx.fillStyle = hpFrac > 0.5 ? '#10b981' : hpFrac > 0.25 ? '#f59e0b' : '#ef4444';
    ctx.fillRect(s.x - barW / 2, s.y - mechR - 7, barW * hpFrac, barH);

    ctx.restore();
  }

  function drawBeams(beams) {
    beams.forEach((b) => {
      if (!b.path || b.path.length < 2) return;
      const start = worldToScreen(b.path[0][0], b.path[0][1]);
      const end = worldToScreen(b.path[1][0], b.path[1][1]);

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(start.x, start.y);
      ctx.lineTo(end.x, end.y);
      ctx.lineWidth = 3;
      ctx.strokeStyle = b.kind === 'laser' ? '#38bdf8' : '#facc15';
      ctx.shadowColor = ctx.strokeStyle;
      ctx.shadowBlur = 10;
      ctx.stroke();
      ctx.restore();
    });
  }

  function drawHoverInspection() {
    if (!hoveredEntity) {
      document.getElementById('inspectTooltip').classList.add('hidden');
      return;
    }

    const tip = document.getElementById('inspectTooltip');
    tip.classList.remove('hidden');
    tip.innerHTML = hoveredEntity.html;
    tip.style.left = `${hoveredEntity.screenX + 15}px`;
    tip.style.top = `${hoveredEntity.screenY - 15}px`;
  }

  function drawEmptyState() {
    ctx.fillStyle = '#64748b';
    ctx.font = '14px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('NO MATCH LOADED. SELECT A REPLAY OR CLICK "+ SIMULATE MATCH"', canvas.width / 2, canvas.height / 2);
  }

  // --- HUD & Strategy Updates ---
  function updateHUD() {
    if (!currentReplay || !currentReplay.frames || currentReplay.frames.length === 0) return;
    const frame = currentReplay.frames[currentFrameIdx];
    if (!frame) return;

    const h = frame.self;

    // State & Reasoning
    const stateEl = document.getElementById('botState');
    stateEl.textContent = (h.state || 'ROTATE').toUpperCase();
    stateEl.className = `badge badge-state state-${h.state}`;

    document.getElementById('botSubMode').textContent = (h.pacing_mode || h.armer_mode || h.dropper_mode || h.farmer_mode || '-').toUpperCase();
    document.getElementById('botWhy').textContent = h.why || (h.pacing_mode ? `Pacing: ${h.pacing_mode}` : 'Navigating toward optimal zone cover');
    document.getElementById('stateBanner').textContent = (h.pacing_mode || h.state || 'ROTATE').toUpperCase();

    // Vitals
    const hpFrac = (h.hp / (h.max_hp || 1000)) * 100;
    document.getElementById('hpBar').style.width = `${hpFrac}%`;
    document.getElementById('hpText').textContent = `${h.hp.toFixed(0)} / ${(h.max_hp || 1000).toFixed(0)} (${hpFrac.toFixed(0)}%)`;

    const nrgFrac = (h.energy / (h.max_energy || 100)) * 100;
    document.getElementById('energyBar').style.width = `${nrgFrac}%`;
    document.getElementById('energyText').textContent = `${h.energy.toFixed(0)} / ${(h.max_energy || 100).toFixed(0)}`;

    // Stat Grid
    document.getElementById('statCubes').textContent = h.cubes || 0;
    document.getElementById('statDmgBoost').textContent = `+${((h.cubes || 0) * 4)}%`;
    document.getElementById('statStrafe').textContent = h.strafe ? 'ACTIVE' : 'OFF';

    // Top Header Pills
    document.getElementById('cubesPill').textContent = `${h.cubes || 0} CUBES`;
    document.getElementById('modePill').textContent = (h.mode || 'PRACTICE').toUpperCase();
    document.getElementById('killsPill').textContent = `${currentReplay.kills || 0} KILLS`;

    // Weapons
    const w0 = (h.weapons && h.weapons[0]) || h.slot0 || {};
    const w1 = (h.weapons && h.weapons[1]) || h.slot1 || null;

    document.getElementById('gunAmmo').textContent = `AMMO: ${w0.ammo ?? 12} / 12`;
    document.getElementById('gunStatus').textContent = w0.reload > 0 ? `RELOAD (${w0.reload.toFixed(1)}s)` : w0.cd > 0 ? `CD (${w0.cd.toFixed(2)}s)` : 'READY';

    if (w1) {
      document.getElementById('auxWeaponName').textContent = (w1.kind || 'LIGHTNING').toUpperCase();
      document.getElementById('auxWeaponStats').textContent = w1.kind === 'lightning' ? '240 DPS | 45m AUTO' : w1.kind === 'laser' ? 'SNIPER | 230m BEAM' : 'ARTILLERY';
      document.getElementById('auxWeaponStatus').textContent = w1.cd > 0 ? `CD ${w1.cd.toFixed(1)}s` : 'READY';
    } else {
      document.getElementById('auxWeaponName').textContent = 'EMPTY (SLOT 1)';
      document.getElementById('auxWeaponStats').textContent = 'SEEKING LIGHTNING <= 200m';
      document.getElementById('auxWeaponStatus').textContent = 'UNARMED';
    }

    // Zone
    if (frame.zone) {
      document.getElementById('zoneCurRadius').textContent = `${frame.zone.radius.toFixed(0)} m`;
      document.getElementById('zoneNextRadius').textContent = `${frame.zone.next_radius.toFixed(0)} m`;
      document.getElementById('zoneDps').textContent = `${frame.zone.dps || 0} / s`;
    }

    // Engine Debug Strings
    document.getElementById('debugCombat').textContent = h.combat_debug || 'target engaged';
    document.getElementById('debugNav').textContent = h.nav_debug || 'path clear';

    // Time & Tick
    document.getElementById('timeCurrent').textContent = formatTime(frame.t);
    document.getElementById('tickDisplay').textContent = `TICK: ${frame.tick}`;
    document.getElementById('coordDisplay').textContent = `X: ${h.pos[0].toFixed(1)} | Y: ${h.pos[1].toFixed(1)} | Zoom: ${scale.toFixed(1)}x`;
  }

  function formatTime(s) {
    const mins = Math.floor(s / 60);
    const secs = (s % 60).toFixed(1);
    return `${mins.toString().padStart(2, '0')}:${secs.padStart(4, '0')}`;
  }

  // --- Controls & UI Setup ---
  function setupControls() {
    document.getElementById('btnPlayPause').addEventListener('click', togglePlay);
    document.getElementById('btnPrevTick').addEventListener('click', () => seekToFrame(currentFrameIdx - 1));
    document.getElementById('btnNextTick').addEventListener('click', () => seekToFrame(currentFrameIdx + 1));

    document.getElementById('timelineSlider').addEventListener('input', (e) => {
      seekToFrame(parseInt(e.target.value));
    });

    document.querySelectorAll('.btn-speed').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.btn-speed').forEach((b) => b.classList.remove('active'));
        e.target.classList.add('active');
        playSpeed = parseFloat(e.target.dataset.speed);
      });
    });

    document.getElementById('btnFollow').addEventListener('click', () => {
      followBot = !followBot;
      updateFollowBtn();
    });

    document.getElementById('btnResetView').addEventListener('click', resetCameraView);

    document.getElementById('replaySelect').addEventListener('change', (e) => {
      loadReplay(e.target.value);
    });

    // Modal Simulation Controls
    const modal = document.getElementById('simModal');
    document.getElementById('btnNewSim').addEventListener('click', () => modal.classList.remove('hidden'));
    document.getElementById('btnCancelSim').addEventListener('click', () => modal.classList.add('hidden'));
    document.getElementById('btnExecuteSim').addEventListener('click', executeSimulation);

    // Keyboard Shortcuts
    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
      if (e.code === 'Space') {
        e.preventDefault();
        togglePlay();
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        seekToFrame(currentFrameIdx - (e.shiftKey ? 10 : 1));
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        seekToFrame(currentFrameIdx + (e.shiftKey ? 10 : 1));
      } else if (e.code === 'KeyF') {
        followBot = !followBot;
        updateFollowBtn();
      } else if (e.code === 'KeyR') {
        resetCameraView();
      }
    });
  }

  function updateFollowBtn() {
    const btn = document.getElementById('btnFollow');
    if (followBot) btn.classList.add('active');
    else btn.classList.remove('active');
  }

  async function executeSimulation() {
    const seed = document.getElementById('simSeed').value;
    const preset = document.getElementById('simPreset').value;
    const modal = document.getElementById('simModal');
    modal.classList.add('hidden');

    const btn = document.getElementById('btnNewSim');
    btn.textContent = 'Simulating...';
    btn.disabled = true;

    try {
      const res = await fetch('/api/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seed: parseInt(seed), preset: preset }),
      });
      const replay = await res.json();
      btn.textContent = '+ Simulate Match';
      btn.disabled = false;

      await loadReplayList();
      document.getElementById('replaySelect').value = replay.id;
      await loadReplay(replay.id);
      play();
    } catch (e) {
      alert(`Simulation failed: ${e.message}`);
      btn.textContent = '+ Simulate Match';
      btn.disabled = false;
    }
  }

  function setupLayerToggles() {
    const bindToggle = (id, key) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('change', (e) => {
        layers[key] = e.target.checked;
        requestRedraw();
      });
    };
    bindToggle('layerMap', 'map');
    bindToggle('layerZone', 'zone');
    bindToggle('layerPath', 'path');
    bindToggle('layerEngage', 'engage');
    bindToggle('layerLightning', 'lightning');
    bindToggle('layerSafe', 'safe');
    bindToggle('layerHunters', 'hunters');
    bindToggle('layerDrops', 'drops');
    bindToggle('layerEconomy', 'economy');
  }

  function setupCanvasInteractions() {
    canvas.addEventListener('mousedown', (e) => {
      if (e.button === 0) {
        isDragging = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        followBot = false;
        updateFollowBtn();
      }
    });

    window.addEventListener('mousemove', (e) => {
      if (isDragging) {
        const dx = e.clientX - dragStartX;
        const dy = e.clientY - dragStartY;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        camX -= dx / scale;
        camY += dy / scale;
        requestRedraw();
      }

      // Track world mouse for hover tooltip
      const rect = canvas.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      mouseWorld = screenToWorld(sx, sy);
      inspectAtMouse(sx, sy);
    });

    window.addEventListener('mouseup', () => {
      isDragging = false;
    });

    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
      const rect = canvas.getBoundingClientRect();
      const mouseSX = e.clientX - rect.left;
      const mouseSY = e.clientY - rect.top;

      const before = screenToWorld(mouseSX, mouseSY);
      scale = Math.max(0.5, Math.min(10.0, scale * zoomFactor));
      const after = screenToWorld(mouseSX, mouseSY);

      camX += before.x - after.x;
      camY += before.y - after.y;
      requestRedraw();
    });
  }

  function inspectAtMouse(sx, sy) {
    if (!currentReplay || !currentReplay.frames) return;
    const frame = currentReplay.frames[currentFrameIdx];
    if (!frame) return;

    let found = null;
    const maxScreenDist = 18;

    // Check Hero Mech
    if (frame.self) {
      const s = worldToScreen(frame.self.pos[0], frame.self.pos[1]);
      if (Math.hypot(sx - s.x, sy - s.y) <= maxScreenDist) {
        found = {
          screenX: sx,
          screenY: sy,
          html: `<strong>OUR BOT</strong><br>State: ${frame.self.state}<br>HP: ${frame.self.hp.toFixed(0)}<br>Energy: ${frame.self.energy.toFixed(0)}<br>Cubes: ${frame.self.cubes}`,
        };
      }
    }

    // Check Hunters
    if (!found && frame.mechs) {
      for (const h of frame.mechs) {
        const s = worldToScreen(h.pos[0], h.pos[1]);
        if (Math.hypot(sx - s.x, sy - s.y) <= maxScreenDist) {
          const d = frame.self ? Math.hypot(h.pos[0] - frame.self.pos[0], h.pos[1] - frame.self.pos[1]) : 0;
          found = {
            screenX: sx,
            screenY: sy,
            html: `<strong>HUNTER ${h.id}</strong><br>Tier: ${h.tier.toUpperCase()}<br>HP: ${h.hp.toFixed(0)}<br>Distance: ${d.toFixed(1)}m<br>Status: ${h.active ? 'HUNTING US' : 'ROAMING'}`,
          };
          break;
        }
      }
    }

    // Check Drops
    if (!found && frame.drops) {
      for (const d of frame.drops) {
        const s = worldToScreen(d.pos[0], d.pos[1]);
        if (Math.hypot(sx - s.x, sy - s.y) <= maxScreenDist) {
          found = {
            screenX: sx,
            screenY: sy,
            html: `<strong>SUPPLY DROP</strong><br>Status: ${d.lands_in > 0 ? `Landing in ${d.lands_in}s` : 'LANDED'}<br>Capture Progress: ${d.progress.toFixed(1)}s / 4.0s`,
          };
          break;
        }
      }
    }

    hoveredEntity = found;
  }
})();
