// Craft Lab in Club Coders Live (CHANGE 202): the island of blocks, its players, creatures, Craft Bots and things
// dropped, drawn from the class server's world and snapshots, and a learner (or the teacher, in the world in creative)
// playing on the page as in the window (craft/craft_client.py): your own player predicted as the window predicts it
// (craft_sim.js: craft_sim.py's step, ported line for line), digging and placing shown at once and the server's to keep.
//
// The world comes as the window's does: a world_head message, the blocks and their meta zipped in binary parts (kind 9,
// a two-byte index), then the world message; the page inflates them (the browser's own DecompressionStream), works the
// light out as craft_world does (the sky's straight down each open column and the glowsticks', spread a level less a
// block) and meshes the chunks near the camera with craft_mesh.js (craft_mesh.py's open faces, corner shading and baked
// light, byte for byte), nearest first and a few milliseconds a frame, again where a block changes. The blocks' and
// items' tables and the atlas are craft.json and tex/craft_atlas.png (make_craft.py: craft_art's own atlas); the
// server's own blocks (mods/blocks.py) are painted into it here as the window paints them.
//
// The look is the window's on every tier (craft_gfx.py): Craft Lab's own shader (the atlas's pixels times the corner
// shading and the light baked into each corner, 0 to 12, each level 0.757 of the one above; the sky's part of it times
// the time of day, the glowsticks' a cool cyan-white and the same all night, a held Glowfruit's round your eyes; the
// Server Rack's tiles playing their frames; fog into the sky's colour at the edge of the view; VIEW metres a tier: mesh
// 72, lines 96, blocks 64, low 80, medium 112, high 144, ultra 224), sun shadows from medium (a shadow map that follows
// you), waving leaves, plants and water on high and ultra; the 15-minute day's sky: a dome deepening overhead, a round
// sun in a soft glow (a coral or amber halo at dusk and dawn) and a round moon crossing it, the stars at night (the
// window's 500: craft.json's sky), soft puff clouds at two heights drifting east (low and up, more each tier up:
// tex/craft_clouds.png); mesh and lines are the engine's line looks (black faces, every face's edges on mesh, only the
// folds and where the block changes on lines, fading into the dark). The creatures, players, Craft Bots and things
// dropped are craft_models' boxes with the atlas's faces, lit by where they stand (the visors' and the Glitches' and
// Rust Walkers' eyes shining in the dark), their legs and arms swinging, a red flash when hurt, the suit each player
// wears (the roster's wear: visor, vest, boots); the held item at the bottom right, the block you look at in a cyan
// glow outline, its faces dissolving pixel by pixel to the night navy as you dig, bits flying, the Overload Cell's
// glow and pulse and a Glitch's streak home (Effects: the server's armed, ring and streak).

/* global BABYLON */

import {BaseScene, TIERS, v3, tierSettings, mulberry, applyResolution, getLineColour} from "./base3d.js";
import {CRAFT_FIELDS, KIND_SNAPSHOT, kindOf as frameKind, unpackSnapshot} from "./wire.js";
import * as sim from "./craft_sim.js";
import {Tables, meshChunk, CHUNK, CORNERS, FACE_SHADE, UV} from "./craft_mesh.js";
import {Predictor, InputLog, ErrorSmoother, LeadController, quantiseInput, packInput, seqDiff, SEQ_MASK} from "./predict.js";
import {CraftHud, CraftScreen, CraftMenu, setAtlas, TOOLBELT, REACH as FAB_REACH, iconTile} from "./craft_ui.js";
import {LEARNER_TABS} from "./learner.js";
import {TEACHER_TABS} from "./teacher.js";

const $ = id => document.getElementById(id);
const DEG = Math.PI / 180;
const KIND_WORLD = 9;  // (a binary frame's first byte: a part of the world, craft_server.KIND_WORLD)
export const VIEW = {mesh: 72, lines: 96, blocks: 64, low: 80, medium: 112, high: 144, ultra: 224};
const SHADOW_AREA = {medium: 64.0, high: 96.0, ultra: 128.0};
// (the window's shadow bias is 0.0035 of its sun lens's depth; the page's depth texture is read a little differently, and
// this much less gives the window's picture: the shadows of the tall grass and under a block's edge, no stripes)
const SHADOW_BIAS = 0.0008;
const WAVES = new Set(["high", "ultra"]);
const CLOUDS = {mesh: 0, lines: 0, blocks: 0, low: 9, medium: 14, high: 18, ultra: 26};  // (each of two heights)
const PARTICLES = {mesh: 6, lines: 6, blocks: 8, low: 10, medium: 14, high: 18, ultra: 24};
const SPARKS = {mesh: 16, lines: 16, blocks: 18, low: 22, medium: 30, high: 38, ultra: 48};
// the brand's colours (the website's tokens: craft_gfx.BG, CYAN, MAGENTA)
const BG = [0x09 / 255, 0x0c / 255, 0x17 / 255], CYAN = [0x3e / 255, 0xe9 / 255, 0xff / 255], MAGENTA = [0xff / 255, 0x4f / 255, 0xd8 / 255];
const ANIM_FRAMES = 4, ANIM_RATE = 4.0;   // (an animated tile's frames side by side in its atlas row, 4 a second)
// the sky through the day (craft_gfx: the 15-minute day's phases, the horizon's colour, the fog's too, and overhead's)
const GFX_NIGHT = 10.0 / 15, SUNSET = (0.6 + GFX_NIGHT) / 2, SUNRISE = (14.0 / 15 + 1.0) / 2, GLOW_WINDOW = 0.042;
const SKY_DAY = [0.6, 0.78, 0.98], TOP_DAY = [0.26, 0.5, 0.94];
const SKY_DUSK = [0.98, 0.5, 0.45], TOP_DUSK = [0.42, 0.24, 0.52];
const SKY_DAWN = [0.99, 0.74, 0.47], TOP_DAWN = [0.42, 0.52, 0.8];
const SKY_NIGHT = [0.055, 0.075, 0.14], TOP_NIGHT = BG;
const VIEWS = ["eyes", "behind", "front"];
const VIEW_NAMES = {eyes: "your eyes", behind: "behind you", front: "in front of you", free: "flying free", follow: "following"};
const MOUSE_SPEED = 0.12;   // degrees a pixel
const PLACE_GAP = 0.22;
const AIR = 12.0;   // (craft_game.AIR: seconds under water before you take 5 Health a second)
const DUSK = 0.6, NIGHT = 9.999 / 15, DAWN = 14.0 / 15;   // (craft_game's day: dusk, night from NIGHT, dawn from DAWN)
const TIMES = [["dawn", "Dawn"], ["day", "Day"], ["dusk", "Dusk"], ["night", "Night"], ["cycle", "Day and night"]];
// the suit's pieces in their material's look (craft_models.SUIT_TILES), names' heights over a player and a Bot
const SUIT_TILES = {fluff: "fluff_white", copper: "copper_block", iron: "iron_block", neon: "neon_block"};
const TAG_Z = {player: 2.0, bot: 1.6};
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const wrapDeg = d => ((d + 180) % 360 + 360) % 360 - 180;

// ---------- the tables and the atlas (craft.json, tex/craft_atlas.png: make_craft.py) ----------
let dataPromise = null;
let skyData = null;  // (craft.json's sky: craft_gfx's stars, where the clouds start, the dig mask's order)
export function loadCraftData() {
    if (!dataPromise) {
        dataPromise = Promise.all([
            fetch("craft.json").then(r => (r.ok ? r.json() : Promise.reject(new Error(`craft.json: ${r.status}`)))),
            new Promise((ok, bad) => {
                const img = new Image();
                img.onload = () => ok(img);
                img.onerror = () => bad(new Error("tex/craft_atlas.png didn't load"));
                img.src = "tex/craft_atlas.png";
            }),
        ]).then(([data, img]) => { skyData = data.sky || null; return {data, img}; });
        dataPromise.catch(() => { dataPromise = null; });
    }
    return dataPromise;
}

// the atlas with the server's own blocks painted in (craft_art.build_atlas: a plain tile in the block's colour, a
// little noise in it), as a canvas, and where every tile is
function paintAtlas(data, img) {
    const n = data.atlas.tiles, T = data.atlas.tile, canvas = document.createElement("canvas");
    canvas.width = canvas.height = n * T;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0);
    const where = Object.assign({}, data.atlas.where);
    let next = data.atlas.used;
    for (const b of sim.B.blocks) {
        if (!b.mod) continue;
        const name = b.tiles[1];
        if (where[name] || next >= n * n) continue;
        const col = next % n, row = Math.floor(next / n);
        next++;
        where[name] = [col, row];
        const c = b.colour || [200, 200, 200], rnd = mulberry(name.length * 7919 + c[0] * 31 + c[1] * 7 + c[2]);
        const im = ctx.createImageData(T, T);
        for (let i = 0; i < T * T; i++) {
            const k = (rnd() - 0.5) * 28;
            im.data[i * 4] = clamp(c[0] + k, 0, 255); im.data[i * 4 + 1] = clamp(c[1] + k, 0, 255);
            im.data[i * 4 + 2] = clamp(c[2] + k, 0, 255); im.data[i * 4 + 3] = 255;
        }
        ctx.putImageData(im, col * T, row * T);
    }
    return {canvas, where, url: canvas.toDataURL("image/png")};
}

// a tile's corner in the atlas and its size, a hair inside it (craft_gfx.uv_of)
function uvOf(where, name, tiles = 16, inset = true) {
    const [col, row] = where[name] || [0, 0], s = 1.0 / tiles, e = inset ? s / 32 : 0;
    return [col * s + e, 1.0 - (row + 1) * s + e, s - 2 * e];
}

// ---------- the time of day (craft_gfx.sky_look, time_look) ----------
const smooth = x => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
const mix3 = (a, b, f) => a.map((v, i) => v + (b[i] - v) * f);

// the sun's way round (0 at sunrise, pi at sunset, 1.5 pi at midnight) at the time of day t (craft_gfx.sun_angle)
function sunAngle(t) {
    const up = 1.0 - (SUNRISE - SUNSET), s = (((t - SUNRISE) % 1.0) + 1.0) % 1.0;
    return s < up ? Math.PI * s / up : Math.PI + Math.PI * (s - up) / (1.0 - up);
}

// 1 all day, 0 all night, a smooth step through dusk and dawn (craft_gfx.day_amount)
function dayAmount(t) {
    t = ((t % 1) + 1) % 1;
    if (t < DUSK) return 1.0;
    if (t < GFX_NIGHT) return 1.0 - smooth((t - DUSK) / (GFX_NIGHT - DUSK));
    if (t < DAWN) return 0.0;
    return smooth((t - DAWN) / (1.0 - DAWN));
}

// everything the time of day decides (craft_gfx.sky_look, set_time): the daylight (0.14 to 1), day (0 to 1), dusk and
// dawn (their colours' share), the sky at the horizon (the fog's colour) and overhead, the sun's direction (game
// axes), the sky light's tint
export function timeLook(t) {
    t = ((t % 1) + 1) % 1;
    const day = dayAmount(t);
    const dusk = Math.max(0, 1 - Math.abs(t - SUNSET) / GLOW_WINDOW);
    const dRise = Math.min(Math.abs(t - SUNRISE), Math.abs(t - SUNRISE + 1.0));
    const dawn = Math.max(0, 1 - dRise / GLOW_WINDOW);
    let sky = mix3(SKY_NIGHT, SKY_DAY, day);
    sky = mix3(sky, SKY_DUSK, smooth(dusk) * 0.8);
    sky = mix3(sky, SKY_DAWN, smooth(dawn) * 0.7);
    let top = mix3(TOP_NIGHT, TOP_DAY, day);
    top = mix3(top, TOP_DUSK, smooth(dusk) * 0.7);
    top = mix3(top, TOP_DAWN, smooth(dawn) * 0.6);
    const a = sunAngle(t);
    let d = [Math.cos(a) * 0.9, 0.35, Math.sin(a)];
    const l = Math.hypot(...d);
    d = d.map(v => v / l);
    const daylight = 0.14 + 0.86 * day;
    const tint = daylight > 0.6 ? [1, 1, 1] : [0.75 + 0.25 * daylight, 0.8 + 0.2 * daylight, 1.0];
    return {daylight, day, dusk, dawn, sky, zenith: top, sunDir: d, tint};
}

// ---------- the shaders (craft_gfx's, in Babylon's axes: the game's z is Babylon's y) ----------
// (the light's curve: each level 0.757 of the one above, so full light is 1 and 0 as dark as it always was; a vertex's
// fourth byte: its face x 32, + 16 where it waves, + 8 on a tile whose frames play; u_held: a light carried, its place
// in Babylon's axes and its level; u_dig: the block being dug, in Babylon's axes, and how far, its pixels going to navy)
const CHUNK_VERT = `
precision highp float;
attribute vec3 position;
attribute vec2 uv;
attribute vec4 cdata;
uniform mat4 world;
uniform mat4 viewProjection;
uniform vec3 cameraPosition;
uniform float u_day;
uniform vec3 u_tint;
uniform float u_time;
uniform float u_wave;
uniform vec4 u_held;
varying vec2 vUV;
varying vec3 vLight;
varying float vDist;
varying float vSunny;
varying vec3 vCell;
varying float vFace;
#ifdef SHADOWS
uniform mat4 shadowMatrix;
varying vec4 vShadow;
#endif
float level(float x) { return pow(LIGHT_FALL, (1.0 - x) * LIGHT_MAX); }
void main(void) {
    vec4 p = world * vec4(position, 1.0);
    float flags = floor(cdata.a * 255.0 + 0.5);
    float face = floor(flags / 32.0);
    float low = mod(flags, 32.0);
    float wave = low >= 16.0 ? 1.0 : 0.0;
    float anim = mod(low, 16.0) >= 8.0 ? 1.0 : 0.0;
    if (u_wave > 0.5 && wave > 0.5) {
        float gx = p.x + sin(u_time * 1.7 + p.z * 0.9 + p.y) * 0.04;
        p.z += cos(u_time * 1.3 + gx * 0.8) * 0.04;
        p.x = gx;
    }
    gl_Position = viewProjection * p;
    vec2 tuv = uv;
    tuv.x += anim * mod(floor(u_time * ANIM_RATE), ANIM_FRAMES) * TILE_U;
    vUV = tuv;
    float sky = level(cdata.g) * u_day;
    float blk = cdata.b > 0.01 ? level(cdata.b) : 0.0;
    float held = u_held.w - distance(p.xyz, u_held.xyz);
    blk = held > 0.0 ? max(blk, level(held / LIGHT_MAX)) : blk;
    vec3 l = max(vec3(sky) * u_tint, vec3(blk * 0.84, blk * 0.95, blk));
    vLight = max(l, vec3(0.045)) * cdata.r;
    vSunny = cdata.g * u_day;
    vec3 n = face < 0.5 ? vec3(1.0, 0.0, 0.0) : face < 1.5 ? vec3(-1.0, 0.0, 0.0) : face < 2.5 ? vec3(0.0, 0.0, 1.0) :
             face < 3.5 ? vec3(0.0, 0.0, -1.0) : face < 4.5 ? vec3(0.0, 1.0, 0.0) : vec3(0.0, -1.0, 0.0);
    vCell = p.xyz - n * 0.02;
    vFace = face;
    vDist = distance(p.xyz, cameraPosition);
#ifdef SHADOWS
    vShadow = shadowMatrix * p;
#endif
}`;
const CHUNK_FRAG = `
precision highp float;
uniform sampler2D atlas;
uniform vec3 u_fog_colour;
uniform vec2 u_fog;
uniform float u_cut;
uniform float u_alpha;
uniform float u_time;
uniform vec4 u_dig;
uniform vec4 baseColor;
varying vec2 vUV;
varying vec3 vLight;
varying float vDist;
varying float vSunny;
varying vec3 vCell;
varying float vFace;
#ifdef SHADOWS
uniform highp sampler2DShadow shadowMap;
uniform float shadowBias;
varying vec4 vShadow;
#endif
float hash(vec2 q) {
    vec3 p3 = fract(vec3(q.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}
void main(void) {
    vec4 t = texture2D(atlas, vUV);
    if (t.a < u_cut) discard;
    vec3 c = t.rgb * vLight;
    float a = t.a * u_alpha;
#ifdef SHADOWS
    vec3 sc = vShadow.xyz / vShadow.w;
    vec2 suv = sc.xy * 0.5 + 0.5;
    float lit = 1.0;
    if (suv.x > 0.0 && suv.x < 1.0 && suv.y > 0.0 && suv.y < 1.0 && sc.z < 1.0) lit = texture(shadowMap, vec3(suv, sc.z * 0.5 + 0.5 - shadowBias));
    c *= 1.0 - 0.36 * (1.0 - lit) * clamp(vSunny * 1.4 - 0.25, 0.0, 1.0);
#endif
    if (u_dig.w > 0.0) {
        vec3 d = abs(floor(vCell) - u_dig.xyz);
        if (d.x + d.y + d.z < 0.5) {
            vec2 px = floor(vUV * ATLAS_PX);
            float h = hash(px + vec2(vFace * 41.0, vFace * 13.0));
            if (h < u_dig.w) {
                c = vec3(BG_RGB);
                a = 1.0;
            } else if (h < u_dig.w + 0.12 && hash(px + vec2(floor(u_time * 10.0) * 7.0, 3.0)) > 0.55) {
                c = mix(c, vec3(BG_RGB), 0.7);
            }
        }
    }
    float f = clamp((vDist - u_fog.x) / (u_fog.y - u_fog.x), 0.0, 1.0);
    gl_FragColor = vec4(mix(c, u_fog_colour, f), a) * baseColor;
}`;
const ENT_VERT = `
precision highp float;
attribute vec3 position;
attribute vec2 uv;
attribute vec4 color;
uniform mat4 world;
uniform mat4 viewProjection;
uniform vec3 cameraPosition;
uniform float u_day;
uniform vec3 u_tint;
uniform vec2 u_here;
uniform vec4 u_held;
varying vec2 vUV;
varying vec3 vLight;
varying vec4 vCol;
varying float vDist;
float level(float x) { return pow(LIGHT_FALL, (1.0 - x) * LIGHT_MAX); }
void main(void) {
    vec4 p = world * vec4(position, 1.0);
    gl_Position = viewProjection * p;
    vUV = uv;
    float sky = level(u_here.x) * u_day;
    float blk = u_here.y > 0.01 ? level(u_here.y) : 0.0;
    float held = u_held.w - distance(p.xyz, u_held.xyz);
    blk = held > 0.0 ? max(blk, level(held / LIGHT_MAX)) : blk;
    vLight = max(max(vec3(sky) * u_tint, vec3(blk * 0.84, blk * 0.95, blk)), vec3(0.06));
    vCol = color;
    vDist = distance(p.xyz, cameraPosition);
}`;
const ENT_FRAG = `
precision highp float;
uniform sampler2D atlas;
uniform vec3 u_fog_colour;
uniform vec2 u_fog;
uniform vec4 u_flash;
uniform vec4 baseColor;
varying vec2 vUV;
varying vec3 vLight;
varying vec4 vCol;
varying float vDist;
void main(void) {
    vec4 t = texture2D(atlas, vUV);
    if (t.a < 0.3) discard;
    vec3 c = t.rgb * vCol.rgb * vLight;
    c = mix(c, u_flash.rgb, u_flash.a);
    float f = clamp((vDist - u_fog.x) / (u_fog.y - u_fog.x), 0.0, 1.0);
    gl_FragColor = vec4(mix(c, u_fog_colour, f), t.a * vCol.a) * baseColor;
}`;
const DEPTH_VERT = `
precision highp float;
attribute vec3 position;
attribute vec2 uv;
uniform mat4 world;
uniform mat4 viewProjection;
varying vec2 vUV;
void main(void) { vUV = uv; gl_Position = viewProjection * world * vec4(position, 1.0); }`;
const DEPTH_FRAG = `
precision highp float;
uniform sampler2D atlas;
varying vec2 vUV;
void main(void) { if (texture2D(atlas, vUV).a < 0.5) discard; gl_FragColor = vec4(1.0); }`;
// the sky's, the outline's and the effects' flat colours (no light, no fog, as the window's setLightOff, setShaderOff,
// setFogOff): a colour times the vertices' and a picture's; STROKE: a line a few pixels wide, its edges smoothed
// (uv: the half width and how far across, in pixels)
const FLAT_VERT = `
precision highp float;
attribute vec3 position;
#if defined(TEX) || defined(STROKE)
attribute vec2 uv;
varying vec2 vUV;
#endif
#ifdef VCOL
attribute vec4 color;
varying vec4 vCol;
#endif
uniform mat4 worldViewProjection;
uniform float u_point;
void main(void) {
    gl_Position = worldViewProjection * vec4(position, 1.0);
    gl_PointSize = u_point;
#if defined(TEX) || defined(STROKE)
    vUV = uv;
#endif
#ifdef VCOL
    vCol = color;
#endif
}`;
const FLAT_FRAG = `
precision highp float;
uniform vec4 u_colour;
uniform vec4 baseColor;
#ifdef TEX
uniform sampler2D tex;
#endif
#if defined(TEX) || defined(STROKE)
varying vec2 vUV;
#endif
#ifdef VCOL
varying vec4 vCol;
#endif
void main(void) {
    vec4 c = u_colour;
#ifdef VCOL
    c *= vCol;
#endif
#ifdef TEX
    c *= texture2D(tex, vUV);
#endif
#ifdef STROKE
    c.a *= clamp(vUV.x + 0.5 - abs(vUV.y), 0.0, 1.0);
#endif
    if (c.a < 0.003) discard;
    gl_FragColor = c * baseColor;
}`;

// a shader's text with Craft Lab's numbers filled in (craft_gfx._source)
function source(text) {
    const L = sim.B.lightMax || 12, fall = Math.pow(0.8, 15.0 / L), f = v => Number(v).toFixed(6);
    return text.replace(/LIGHT_FALL/g, f(fall)).replace(/LIGHT_MAX/g, Number(L).toFixed(1))
        .replace(/ANIM_RATE/g, ANIM_RATE.toFixed(1)).replace(/ANIM_FRAMES/g, ANIM_FRAMES.toFixed(1))
        .replace(/TILE_U/g, (1.0 / 16).toFixed(8)).replace(/ATLAS_PX/g, (16 * 16).toFixed(1))
        .replace(/BG_RGB/g, BG.map(c => c.toFixed(5)).join(", "));
}

function register() {
    const S = BABYLON.Effect.ShadersStore;
    if (S.craftChunkVertexShader) return;
    S.craftChunkVertexShader = source(CHUNK_VERT); S.craftChunkFragmentShader = source(CHUNK_FRAG);
    S.craftEntVertexShader = source(ENT_VERT); S.craftEntFragmentShader = ENT_FRAG;
    S.craftDepthVertexShader = DEPTH_VERT; S.craftDepthFragmentShader = DEPTH_FRAG;
    S.craftFlatVertexShader = FLAT_VERT; S.craftFlatFragmentShader = FLAT_FRAG;
}

// ---------- boxes (craft_gfx.box_geom, card_geom, bit_geom) ----------
// boxes [[lo, hi, tiles (one name or six), colour 0..1]] as one geometry in Babylon's axes: each face's corner colour
// is the face's shade times the box's colour (game corners turned round for Babylon: (x, y, z) -> (x, z, y), and each
// triangle's winding the other way, as the swap mirrors it)
function boxGeo(where, parts) {
    const pos = [], uv = [], col = [], idx = [];
    for (const [lo, hi, tiles, c] of parts) {
        const names = typeof tiles === "string" ? [tiles, tiles, tiles, tiles, tiles, tiles] : tiles;
        for (let d = 0; d < 6; d++) {
            const [u0, v0, s] = uvOf(where, names[d]), sh = FACE_SHADE[d], n = pos.length / 3;
            CORNERS[d].forEach((k, q) => {
                const x = lo[0] + (hi[0] - lo[0]) * k[0], y = lo[1] + (hi[1] - lo[1]) * k[1], z = lo[2] + (hi[2] - lo[2]) * k[2];
                pos.push(x, z, y);
                uv.push(u0 + UV[q][0] * s, v0 + UV[q][1] * s);
                col.push(c[0] * sh, c[1] * sh, c[2] * sh, 1);
            });
            idx.push(n, n + 2, n + 1, n, n + 3, n + 2);
        }
    }
    return {pos, uv, col, idx};
}

function cardGeo(where, tile, size) {  // a flat square showing one tile, both sides
    const [u0, v0, s] = uvOf(where, tile), h = size / 2, pos = [], uv = [], col = [], idx = [];
    for (const [side, ys] of [[0, -0.004], [1, 0.004]]) {
        let corners = [[-h, ys, -h], [h, ys, -h], [h, ys, h], [-h, ys, h]], uvs = [[0, 0], [1, 0], [1, 1], [0, 1]];
        if (side) { corners = corners.reverse(); uvs = uvs.reverse(); }
        const n = pos.length / 3;
        corners.forEach(([x, y, z], q) => { pos.push(x, z, y); uv.push(u0 + uvs[q][0] * s, v0 + uvs[q][1] * s); col.push(1, 1, 1, 1); });
        idx.push(n, n + 2, n + 1, n, n + 3, n + 2);
    }
    return {pos, uv, col, idx};
}

// an item to hold or to see dropped: a block as a small cube of its own faces, anything else its icon on a card
function itemGeo(where, id, size = 0.25) {
    const it = sim.B.items.get(id);
    if (!it) return boxGeo(where, [[[0, 0, 0], [size, size, size], "particle", [1, 0, 1]]]);
    const b = it.block !== null && it.block !== undefined ? sim.B.blocks[it.block] : null;
    if (b && b.shape === "cube" && b.tiles) {
        const [top, side, bottom] = b.tiles, h = size / 2;
        return boxGeo(where, [[[-h, -h, -h], [h, h, h], [side, side, side, side, top, bottom], [1, 1, 1]]]);
    }
    return cardGeo(where, iconTile(id), size);
}

// ---------- pictures made here (craft_gfx.sun_image, moon_image, ring_image, dot_image) ----------
// rgba bytes, the bottom row first (the window's image_texture turns its rows the same way): fn(x, y, r) gives
// [r, g, b, a] 0..1 for each pixel's centre, x and y from -1 to 1, y up
function picture(n, fn) {
    const out = new Uint8Array(n * n * 4);
    for (let row = 0; row < n; row++) {
        const y = (row + 0.5) / n * 2 - 1;
        for (let col = 0; col < n; col++) {
            const x = (col + 0.5) / n * 2 - 1, c = fn(x, y, Math.hypot(x, y)), i = (row * n + col) * 4;
            for (let k = 0; k < 4; k++) out[i + k] = Math.floor(clamp(c[k], 0, 1) * 255 + 0.5);
        }
    }
    return out;
}
const clip01 = v => clamp(v, 0, 1);
function sunPicture(x, y, r) {  // a round white-gold disc, its edge smooth, in a soft warm glow that fades to nothing
    const disc = clip01((0.34 - r) / 0.025), glow = clip01(1 - (r - 0.3) / 0.7) ** 2.4 * 0.7;
    return [1.0, 0.82 + 0.16 * disc, 0.5 + 0.42 * disc, Math.max(disc, glow)];
}
function moonPicture(x, y, r) {  // a round pale disc with a few soft grey seas, in a faint cool glow
    const disc = clip01((0.6 - r) / 0.03);
    let shade = 1;
    for (const [cx, cy, cr] of [[-0.18, 0.16, 0.17], [0.2, -0.1, 0.12], [0.05, 0.3, 0.08], [-0.1, -0.28, 0.1]]) {
        shade -= 0.16 * clip01(1 - Math.hypot(x - cx, y - cy) / cr) ** 0.6;
    }
    shade -= 0.12 * clip01((x + y) * 0.5 + 0.2) * disc;  // (a little darker on one side: it is a ball)
    const glow = clip01(1 - (r - 0.58) / 0.42) ** 2.5 * 0.3;
    return disc > 0 ? [0.84 * shade, 0.89 * shade, 0.98 * shade, Math.max(disc, glow)] : [0.62, 0.8, 1.0, Math.max(disc, glow)];
}
function ringPicture(x, y, r) {  // the Overload pulse's ring: a thin bright cyan circle with a soft glow either side
    const band = Math.exp(-(((r - 0.92) / 0.03) ** 2)) + 0.3 * Math.exp(-(((r - 0.9) / 0.07) ** 2));
    return [CYAN[0] + (1 - CYAN[0]) * clip01(band - 0.6), CYAN[1], CYAN[2], clip01(band) * (r < 1 ? 1 : 0)];
}
const dotPicture = (x, y, r) => [1, 1, 1, clip01(1 - r) ** 2];  // a soft round glow

// (craft_mesh's unit cube, its corners round its middle, in Babylon's axes: the little cubes of sparks)
const CUBE = CORNERS.flatMap(face => face.map(c => [c[0] - 0.5, c[2] - 0.5, c[1] - 0.5]));
const CUBE_IDX = [0, 1, 2, 3, 4, 5].flatMap(d => [0, 1, 2, 0, 2, 3].map(i => d * 4 + i));
const BOX_EDGES = [[[0, 0, 0], [1, 0, 0]], [[1, 0, 0], [1, 1, 0]], [[1, 1, 0], [0, 1, 0]], [[0, 1, 0], [0, 0, 0]],
                   [[0, 0, 1], [1, 0, 1]], [[1, 0, 1], [1, 1, 1]], [[1, 1, 1], [0, 1, 1]], [[0, 1, 1], [0, 0, 1]],
                   [[0, 0, 0], [0, 0, 1]], [[1, 0, 0], [1, 0, 1]], [[1, 1, 0], [1, 1, 1]], [[0, 1, 0], [0, 1, 1]]];

// lines a few pixels wide (Panda's thick lines, smoothed: craft_gfx's LineSegs with setThickness and MLine), as
// quads turned to the camera each frame. A width is the window's (at 720 rows: thicker on a bigger window, as
// craft_gfx.line_px makes them). Points in the game's axes
class Strokes {
    constructor(sc, name, n, mat, alphaIndex = 300) {
        this.sc = sc;
        this.n = n;
        this.segs = Array.from({length: n}, () => ({a: [0, 0, 0], b: [0, 0, 0], w: 2, ca: [1, 1, 1, 1], cb: [1, 1, 1, 1], cap: true}));
        this.pos = new Float32Array(n * 12);
        this.col = new Float32Array(n * 16);
        this.uv = new Float32Array(n * 8);
        const idx = [];
        for (let i = 0; i < n; i++) idx.push(i * 4, i * 4 + 1, i * 4 + 2, i * 4, i * 4 + 2, i * 4 + 3);
        const m = this.mesh = new BABYLON.Mesh(name, sc.scene);
        m.setVerticesData(BABYLON.VertexBuffer.PositionKind, this.pos, true, 3);
        m.setVerticesData(BABYLON.VertexBuffer.ColorKind, this.col, true, 4);
        m.setVerticesData(BABYLON.VertexBuffer.UVKind, this.uv, true, 2);
        m.setIndices(idx);
        m.hasVertexAlpha = true;
        m.material = mat;
        m.renderingGroupId = 1;
        m.alphaIndex = alphaIndex;
        m.isPickable = false;
        m.alwaysSelectAsActiveMesh = true;  // (its quads move every frame: no bounding box to cull by)
        m.ccColour = [1, 1, 1, 1];
    }

    commit() {
        const sc = this.sc, cam = sc.camera, eng = sc.engine, eye = cam.position, tgt = cam.getTarget();
        let fx = tgt.x - eye.x, fy = tgt.y - eye.y, fz = tgt.z - eye.z;
        const fl = Math.hypot(fx, fy, fz) || 1;
        fx /= fl; fy /= fl; fz /= fl;
        const rw = eng.getRenderWidth(), rh = eng.getRenderHeight();
        const css = (eng.getRenderingCanvas() && eng.getRenderingCanvas().clientHeight) || rh;
        const px = Math.max(1, css / 720) * rh / css;  // (render pixels a window pixel)
        const per = 2 * Math.tan(cam.fov / 2) / rw;     // (metres a render pixel, a metre away: the fov is across)
        const P = this.pos, C = this.col, U = this.uv;
        this.segs.forEach((s, i) => {
            const A = [s.a[0], s.a[2], s.a[1]], B = [s.b[0], s.b[2], s.b[1]];
            let dx = B[0] - A[0], dy = B[1] - A[1], dz = B[2] - A[2];
            const dl = Math.hypot(dx, dy, dz);
            const half = s.w * px / 2, hw = half + 1;
            if (dl < 1e-6 || s.w <= 0) { P.fill(0, i * 12, i * 12 + 12); return; }
            dx /= dl; dy /= dl; dz /= dl;
            [[A, -1, s.ca], [B, 1, s.cb]].forEach(([Q, sign, c], e) => {
                const depth = Math.max(0.02, (Q[0] - eye.x) * fx + (Q[1] - eye.y) * fy + (Q[2] - eye.z) * fz), k = depth * per;
                const ext = s.cap ? half * k * sign : 0;
                const qx = Q[0] + dx * ext, qy = Q[1] + dy * ext, qz = Q[2] + dz * ext;
                const vx = qx - eye.x, vy = qy - eye.y, vz = qz - eye.z;
                let sx = dy * vz - dz * vy, sy = dz * vx - dx * vz, sz = dx * vy - dy * vx;
                const sl = Math.hypot(sx, sy, sz) || 1, w = hw * k / sl;
                sx *= w; sy *= w; sz *= w;
                // (corners: A-, A+, B+, B-)
                const v0 = i * 4 + (e === 0 ? 0 : 3), v1 = i * 4 + (e === 0 ? 1 : 2);
                P.set([qx - sx, qy - sy, qz - sz], v0 * 3);
                P.set([qx + sx, qy + sy, qz + sz], v1 * 3);
                C.set(c, v0 * 4); C.set(c, v1 * 4);
                U.set([half, -hw], v0 * 2); U.set([half, hw], v1 * 2);
            });
        });
        const m = this.mesh;
        m.updateVerticesData(BABYLON.VertexBuffer.PositionKind, P);
        m.updateVerticesData(BABYLON.VertexBuffer.ColorKind, C);
        m.updateVerticesData(BABYLON.VertexBuffer.UVKind, U);
    }

    dispose() { this.mesh.dispose(); }
}

// n little glowing cubes in one mesh, moved every frame (craft_gfx._Sparks: one draw, however many)
class Sparks {
    constructor(sc, n, mat, parent = null, name = "sparks") {
        this.n = n;
        this.pos = new Float32Array(n * 72);
        this.col = new Float32Array(n * 96);
        const idx = [];
        for (let i = 0; i < n; i++) for (const k of CUBE_IDX) idx.push(i * 24 + k);
        const m = this.mesh = new BABYLON.Mesh(name, sc.scene);
        m.setVerticesData(BABYLON.VertexBuffer.PositionKind, this.pos, true, 3);
        m.setVerticesData(BABYLON.VertexBuffer.ColorKind, this.col, true, 4);
        m.setIndices(idx);
        m.hasVertexAlpha = true;
        m.material = mat;
        m.renderingGroupId = 1;
        m.alphaIndex = 250;
        m.isPickable = false;
        m.alwaysSelectAsActiveMesh = true;
        m.ccColour = [1, 1, 1, 1];
        if (parent) m.parent = parent;
    }

    set(pos, size, colour) {  // pos [n][3] (the game's axes, round the parent), size [n] metres, colour [n][4]
        for (let i = 0; i < this.n; i++) {
            const p = pos[i], s = size[i], c = colour[i];
            for (let k = 0; k < 24; k++) {
                const q = CUBE[k], o = (i * 24 + k) * 3, oc = (i * 24 + k) * 4;
                this.pos[o] = p[0] + q[0] * s; this.pos[o + 1] = p[2] + q[1] * s; this.pos[o + 2] = p[1] + q[2] * s;
                for (let j = 0; j < 4; j++) this.col[oc + j] = clamp(c[j], 0, 1);
            }
        }
        this.mesh.updateVerticesData(BABYLON.VertexBuffer.PositionKind, this.pos);
        this.mesh.updateVerticesData(BABYLON.VertexBuffer.ColorKind, this.col);
    }
}

// a flat card (both sides): half w across and half h up, a part of a picture (u0, v0, u1, v1)
function cardMesh(sc, name, w, h, mat, uvs = [0, 0, 1, 1]) {
    const m = new BABYLON.Mesh(name, sc.scene), vd = new BABYLON.VertexData();
    const [u0, v0, u1, v1] = uvs;
    vd.positions = [-w, -h, 0, w, -h, 0, w, h, 0, -w, h, 0];
    vd.uvs = [u0, v0, u1, v0, u1, v1, u0, v1];
    vd.indices = [0, 1, 2, 0, 2, 3];
    vd.applyToMesh(m);
    m.material = mat;
    m.isPickable = false;
    m.ccColour = [1, 1, 1, 1];
    return m;
}

// what the Overload Cell and the Glitches show (craft_gfx.Effects; the server's armed, ring and streak messages):
//   armed(x, y, z, seconds)  the cell at block (x, y, z) armed: a magenta glow round it, pulsing about three times a
//                            second and faster as it nears the pulse
//   disarm(x, y, z)          that glow gone at once
//   ring(x, y, z, radius)    the pulse from the block: a cyan ring and sparks out to radius in half a second, a flash
//   streak(x0, y0, z0, x1, y1, z1)   a magenta streak from a Glitch to its rift, 0.4 s
//   clear()                  everything gone
// All of it glowing colour over the picture, no light or fog: the same on every tier (the looks too)
class Effects {
    static RING_TIME = 0.5;
    static STREAK_TIME = 0.4;

    constructor(sc) {
        this.sc = sc;
        this.cells = new Map();
        this.rings = [];
        this.streaks = [];
        this.mat = sc.flatMaterial("ccfx", {vcol: true});
        this.lineMat = sc.flatMaterial("ccfxline", {vcol: true, stroke: true});
        this.boxMat = sc.flatMaterial("ccfxbox", {});
        this.ringMat = sc.flatMaterial("ccfxring", {tex: sc.pictureTexture("ring", 128, ringPicture)});
        this.dotMat = sc.flatMaterial("ccfxflash", {tex: sc.pictureTexture("flash", 32, dotPicture)});
    }

    armed(x, y, z, seconds = 3.0) {
        const key = [Math.floor(x), Math.floor(y), Math.floor(z)];
        this.disarm(...key);
        const node = new BABYLON.TransformNode("armed", this.sc.scene);
        node.position = v3(key[0] + 0.5, key[1] + 0.5, key[2] + 0.5);
        const g = {pos: [], idx: []};
        for (let d = 0; d < 6; d++) {
            const n = g.pos.length / 3;
            for (const c of CORNERS[d]) g.pos.push(c[0] - 0.5, c[2] - 0.5, c[1] - 0.5);
            g.idx.push(n, n + 1, n + 2, n, n + 2, n + 3);
        }
        const faces = new BABYLON.Mesh("armed faces", this.sc.scene), vd = new BABYLON.VertexData();
        vd.positions = g.pos;
        vd.indices = g.idx;
        vd.applyToMesh(faces);
        faces.material = this.boxMat;
        faces.parent = node;
        faces.renderingGroupId = 1;
        faces.alphaIndex = 250;
        faces.isPickable = false;
        faces.ccColour = [...MAGENTA, 0.12];
        const edges = new Strokes(this.sc, "armed edges", 12, this.lineMat, 251);
        this.cells.set(key.join(","), {key, node, faces, edges, left: Number(seconds), total: Math.max(0.1, Number(seconds)), phase: 0, beat: 0, done: 0});
        this.cellFrame(this.cells.get(key.join(",")));
    }

    disarm(x, y, z) {
        const k = [Math.floor(x), Math.floor(y), Math.floor(z)].join(","), c = this.cells.get(k);
        if (!c) return;
        c.node.dispose();
        c.edges.dispose();
        this.cells.delete(k);
    }

    cellFrame(c) {
        const beat = c.beat, done = c.done, s = 1.05 + 0.05 * beat + 0.04 * done;
        c.node.scaling.setAll(s);
        c.faces.ccColour = [...MAGENTA, 0.12 + 0.3 * beat + 0.15 * done];
        const a = 0.55 + 0.45 * beat, k = c.key;
        c.edges.segs.forEach((seg, i) => {
            const [p, q] = BOX_EDGES[i];
            seg.a = p.map((v, j) => k[j] + 0.5 + (v - 0.5) * s);
            seg.b = q.map((v, j) => k[j] + 0.5 + (v - 0.5) * s);
            seg.w = 2.0;
            seg.ca = seg.cb = [...MAGENTA, a];
        });
    }

    ring(x, y, z, radius = 2.5) {
        const sc = this.sc, n = SPARKS[sc.tier] || 28;
        const root = new BABYLON.TransformNode("pulse", sc.scene);
        root.position = v3(Math.floor(x) + 0.5, Math.floor(y) + 0.5, Math.floor(z) + 0.5);
        this.disarm(x, y, z);  // (the cell has gone off: its glow goes with it)
        const sparks = new Sparks(sc, n, this.mat, root);
        const card = cardMesh(sc, "ring", 1, 1, this.ringMat);
        card.parent = root;
        card.rotation.x = Math.PI / 2;  // (flat: a ring on the ground round the cell)
        const flash = cardMesh(sc, "flash", 1, 1, this.dotMat);
        flash.parent = root;
        flash.billboardMode = BABYLON.Mesh.BILLBOARDMODE_ALL;
        for (const m of [card, flash]) { m.renderingGroupId = 1; m.alphaIndex = 252; }
        const dirs = [], speeds = [], rises = [];
        for (let i = 0; i < n; i++) {
            const ang = i / n * 2 * Math.PI + (Math.random() * 0.24 - 0.12);
            dirs.push([Math.cos(ang), Math.sin(ang), 0]);
            speeds.push(0.82 + Math.random() * 0.26);
            rises.push(-0.35 + Math.random() * 1.25);
        }
        const r = {root, sparks, card, flash, t: 0, radius: Math.max(0.5, Number(radius)), dirs, speeds, rises};
        this.rings.push(r);
        this.ringFrame(r);
    }

    ringFrame(r) {
        const f = Math.min(1, r.t / Effects.RING_TIME);
        const out = 1 - (1 - f) ** 2.2;  // (fast, then slowing: a shock going out)
        const fade = f < 0.55 ? 1.0 : Math.max(0, 1 - (f - 0.55) / 0.45);
        const white = Math.max(0, 1 - f * 2.5), n = r.dirs.length;
        const pos = r.dirs.map((d, i) => [d[0] * r.radius * out * r.speeds[i], d[1] * r.radius * out * r.speeds[i], r.rises[i] * out * 0.6]);
        const size = new Array(n).fill(0.085 * (1 - 0.5 * f));
        const colour = new Array(n).fill([CYAN[0] + (1 - CYAN[0]) * white, CYAN[1] + (1 - CYAN[1]) * white, 1.0, fade]);
        r.sparks.set(pos, size, colour);
        r.card.scaling.setAll(Math.max(0.05, r.radius * out));
        r.card.ccColour = [1, 1, 1, fade * 0.9];
        r.flash.scaling.setAll(0.4 + 1.6 * f);
        r.flash.ccColour = [0.75, 0.97, 1.0, Math.max(0, 1 - f / 0.35) * 0.9];
    }

    streak(x0, y0, z0, x1, y1, z1) {
        const sc = this.sc;
        const lines = [["glow", 9.0, [...MAGENTA, 0.5]], ["core", 3.5, [1.0, 0.6, 0.93, 1]]].map(([name, w, colour]) => {
            const s = new Strokes(sc, "streak " + name, 9, this.lineMat, name === "core" ? 254 : 253);
            for (const seg of s.segs) { seg.w = w; seg.cap = false; }
            return {s, colour};
        });
        const head = new Sparks(sc, 3, this.mat, null, "streak head");
        const st = {lines, head, t: 0, a: [x0, y0, z0], b: [x1, y1, z1]};
        this.streaks.push(st);
        this.streakFrame(st);
    }

    streakFrame(s) {
        const f = Math.min(1, s.t / Effects.STREAK_TIME);
        const h = 1 - (1 - f) ** 2;  // the head: quick out of the Glitch, easing into the rift
        let tail = f < 1 ? Math.max(0, h - 0.45) : h;
        if (f > 0.6) tail = Math.max(tail, (f - 0.6) / 0.4 * h);
        const {a, b} = s, dist = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]), up = Math.min(1.5, dist * 0.25);
        const at = u => [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u + up * Math.sin(Math.PI * u)];
        const fade = f < 0.8 ? 1.0 : Math.max(0, 1 - (f - 0.8) / 0.2);
        for (const {s: st, colour} of s.lines) {
            const pts = [], cols = [];
            for (let i = 0; i < 10; i++) {
                pts.push(at(tail + (h - tail) * i / 9));
                cols.push([colour[0], colour[1], colour[2], colour[3] * (i / 9) ** 1.5]);
            }
            st.segs.forEach((seg, i) => { seg.a = pts[i]; seg.b = pts[i + 1]; seg.ca = cols[i]; seg.cb = cols[i + 1]; });
            st.mesh.ccColour = [1, 1, 1, fade];
        }
        const p = at(h), jit = () => (Math.random() + Math.random() + Math.random() - 1.5) * 0.06 * 1.41;
        const pos = [0, 1, 2].map(() => [p[0] + jit(), p[1] + jit(), p[2] + jit()]);
        s.head.set(pos, [0.14, 0.09, 0.07], [[1.0, 0.85, 0.97, 1], [...MAGENTA, 1], [...MAGENTA, 1]]);
        s.head.mesh.ccColour = [1, 1, 1, fade];
    }

    update(dt) {
        for (const [k, c] of [...this.cells]) {
            c.left -= dt;
            if (c.left <= 0) { this.disarm(...c.key); continue; }
            c.done = 1 - c.left / c.total;
            c.phase += dt * (3.0 + 4.0 * c.done) * 2 * Math.PI;  // (about 3 a second, 7 by the end)
            c.beat = 0.5 + 0.5 * Math.sin(c.phase);
            this.cellFrame(c);
        }
        this.rings = this.rings.filter(r => {
            r.t += dt;
            if (r.t >= Effects.RING_TIME) { r.root.dispose(); return false; }
            this.ringFrame(r);
            return true;
        });
        this.streaks = this.streaks.filter(s => {
            s.t += dt;
            if (s.t >= Effects.STREAK_TIME) { for (const l of s.lines) l.s.dispose(); s.head.mesh.dispose(); return false; }
            this.streakFrame(s);
            return true;
        });
    }

    commit() {  // (just before the picture: the lines turned to the camera where it is now)
        for (const c of this.cells.values()) c.edges.commit();
        for (const s of this.streaks) for (const l of s.lines) l.s.commit();
    }

    busy() { return !!(this.cells.size || this.rings.length || this.streaks.length); }

    clear() {
        for (const c of [...this.cells.values()]) this.disarm(...c.key);
        for (const r of this.rings) r.root.dispose();
        for (const s of this.streaks) { for (const l of s.lines) l.s.dispose(); s.head.mesh.dispose(); }
        this.rings = [];
        this.streaks = [];
    }
}

// ---------- the scene ----------
export class CraftScene extends BaseScene {
    static TIERS = TIERS;  // (every tier, as the window's craft_gfx)
    static TIER_TEXT = {
        mesh: "mesh: black, and every block face's edges in one colour, the lines behind hidden.",
        lines: "lines: black, the blocks' outlines in one colour (only where the surface folds or the block changes), fading into the dark.",
        blocks: "blocks: Craft Lab's own look nearest you (64 metres), no clouds or shadows: the floor every machine draws.",
        low: "low: 80 metres of the island, soft clouds at two heights.",
        medium: "medium: 112 metres, the sun's shadows, more clouds.",
        high: "high: 144 metres, sharper shadows, the leaves, plants and water moving in the wind.",
        ultra: "ultra: for a strong graphics card: 224 metres of the island, soft shadows reaching far, the most clouds."};

    constructor(canvas, tier, engine) {
        super(canvas, tier, engine, {sky: SKY_DAY});
        register();
        this.world = null;
        this.atlas = null;        // {canvas, where, url}
        this.chunks = new Map();  // "cx,cy" -> {meshes}
        this.todo = new Set();
        this.models = new Map();  // entity id -> Model / ItemModel
        this.bits = [];
        this.time = 0.3;
        this.waveT = 0;
        this.built = 0;
        this.held = [0, -1000, 0, 0];  // (a light carried: its place in Babylon's axes and its level)
        this.dig = [0, -1000, 0, 0];
        this.build();
    }

    setAtlas(atlas, tables) {
        this.atlas = atlas;
        this.tables = tables;
        this.build();
    }

    setWorld(world) {
        this.world = world;
        this.build();
    }

    view() { return VIEW[this.tier] || 112; }
    lineLook() { return this.wire ? (this.wire === "all" ? "mesh" : "lines") : null; }
    shadedTier() { return !this.wire && !!this.mats; }  // (craft_gfx.shaded: the blocks drawn by Craft Lab's shader)

    // (BaseScene.build without the app's lighting: Craft Lab draws with its own shader on every tier)
    build() {
        if (this.scene) this.scene.dispose();
        const settings = this.settings = tierSettings(this.tier);
        applyResolution(this.engine, this.tier);
        const scene = this.scene = new BABYLON.Scene(this.engine);
        scene.skipPointerMovePicking = true;
        scene.clearColor = new BABYLON.Color4(SKY_DAY[0], SKY_DAY[1], SKY_DAY[2], 1);
        this.materials = {};
        this.lineMats = [];
        this.wire = settings.wire || null;
        this.lit = !this.wire;
        this.pbr = false;
        this.lighting = null;
        this.shadows = null;
        if (this.wire) {
            scene.clearColor = new BABYLON.Color4(0, 0, 0, 1);
            const line = sub => (sub.getMaterial() || {}).ccLine ? 1 : 0;
            scene.setRenderingOrder(1, (a, b) => line(a) - line(b));
        }
        const cam = this.camera = new BABYLON.FreeCamera("cam", new BABYLON.Vector3(0, 40, 0), scene);
        cam.inputs.clear();
        cam.minZ = 0.05;
        cam.maxZ = this.view() * 1.2 + 40;
        cam.fovMode = BABYLON.Camera.FOVMODE_HORIZONTAL_FIXED;
        cam.fov = 75 * DEG;
        this.populate();
        scene.onBeforeRenderObservable.add(() => this.beforeRender());
    }

    populate() {
        const scene = this.scene;
        this.chunks = new Map();
        this.models = new Map();
        this.bits = [];
        this.todo = new Set();
        this.chunkRoot = new BABYLON.TransformNode("world", scene);
        this.mats = null;
        this.shaded = [];
        this.rtt = null;
        this.lineCount = 0;
        this.target = null;
        this.effects = null;
        this.sky = null;
        if (!this.atlas) return;
        const look = this.lineLook(), mips = ["medium", "high", "ultra"].includes(this.tier);
        // the atlas: big pixels close to (nearest), mipmapped far off on medium and up, never more than four levels
        // down (a 16-pixel tile is one pixel there), no anisotropic blur (craft_gfx.atlas_texture)
        const tex = this.atlasTex = new BABYLON.DynamicTexture("craft atlas", this.atlas.canvas, scene, mips,
            mips ? BABYLON.Constants.TEXTURE_NEAREST_NEAREST_MIPLINEAR : BABYLON.Constants.TEXTURE_NEAREST_NEAREST);
        tex.hasAlpha = true;
        tex.wrapU = tex.wrapV = BABYLON.Texture.CLAMP_ADDRESSMODE;
        tex.anisotropicFilteringLevel = 1;
        tex.update(true);
        if (mips) this.maxLod(tex, 4);
        const settings = this.settings, gl2 = this.engine.webGLVersion >= 2;
        const shadowSize = !look && SHADOW_AREA[this.tier] && gl2 ? (settings.shadow || 0) : 0;
        if (shadowSize) this.makeShadow(shadowSize);
        const mats = this.mats = {};
        if (look) {
            mats.solid = mats.cutout = mats.blend = mats.ent = this.wireFill();
            mats.lines = this.lineMaterial("craft", 1, this.view() * 0.35, this.view());
            mats.entLines = this.lineMaterial("craftent", 1, this.view() * 0.35, this.view());
        } else {
            mats.solid = this.chunkMaterial("craftsolid", 0.5, 1.0, false, true);
            mats.cutout = this.chunkMaterial("craftcutout", 0.5, 1.0, false, false);
            mats.blend = this.chunkMaterial("craftblend", 0.01, 1.0, true, false);
            mats.ent = this.entMaterial("craftent");
        }
        this.target = this.makeTarget();
        this.effects = new Effects(this);
        this.sky = look ? null : this.makeSky();
        this.particleMat = look ? this.lineInk("bits") : mats.ent;
        if (this.world) {
            for (let cx = 0; cx < this.world.X / CHUNK; cx++) for (let cy = 0; cy < this.world.Y / CHUNK; cy++) this.todo.add(cx + "," + cy);
            this.world.dirty.clear();
        }
        this.applyTime(true);
    }

    maxLod(tex, lod) {  // (WebGL 2: TEXTURE_MAX_LOD on the atlas, as the window's setMaxLod(4))
        try {
            const gl = this.engine._gl, t = tex.getInternalTexture(), res = t && t._hardwareTexture && t._hardwareTexture.underlyingResource;
            if (!gl || !res || this.engine.webGLVersion < 2) return;
            gl.bindTexture(gl.TEXTURE_2D, res);
            gl.texParameterf(gl.TEXTURE_2D, gl.TEXTURE_MAX_LOD, lod);
            gl.bindTexture(gl.TEXTURE_2D, null);
            this.engine.resetTextureCache();
        } catch (e) { /* (an old browser: every level) */ }
    }

    chunkMaterial(name, cut, alpha, blend, cull) {
        const defines = this.rtt ? ["SHADOWS"] : [];
        const m = new BABYLON.ShaderMaterial(name, this.scene, {vertex: "craftChunk", fragment: "craftChunk"}, {
            attributes: ["position", "uv", "cdata"],
            uniforms: ["world", "viewProjection", "cameraPosition", "u_day", "u_tint", "u_time", "u_wave", "u_fog_colour", "u_fog",
                       "u_cut", "u_alpha", "u_held", "u_dig", "baseColor", "shadowMatrix", "shadowBias"],
            samplers: ["atlas", "shadowMap"], defines, needAlphaBlending: blend});
        m.setTexture("atlas", this.atlasTex);
        m.setFloat("u_cut", cut);
        m.setFloat("u_alpha", alpha);
        m.setFloat("u_time", this.waveT % 3600);
        m.setVector4("u_held", new BABYLON.Vector4(...this.held));
        m.setVector4("u_dig", new BABYLON.Vector4(...this.dig));
        m.setColor4("baseColor", new BABYLON.Color4(1, 1, 1, 1));
        m.backFaceCulling = cull;
        if (blend) { m.disableDepthWrite = true; m.alphaMode = BABYLON.Constants.ALPHA_COMBINE; }
        if (this.rtt) {
            m.setInternalTexture("shadowMap", this.rtt.depthStencilTexture);
            m.setFloat("shadowBias", SHADOW_BIAS);
        }
        m.ccChunk = true;
        (this.shaded || (this.shaded = [])).push(m);
        return m;
    }

    entMaterial(name) {
        const m = new BABYLON.ShaderMaterial(name, this.scene, {vertex: "craftEnt", fragment: "craftEnt"}, {
            attributes: ["position", "uv", "color"],
            uniforms: ["world", "viewProjection", "cameraPosition", "u_day", "u_tint", "u_here", "u_held", "u_fog_colour", "u_fog",
                       "u_flash", "baseColor"],
            samplers: ["atlas"], needAlphaBlending: false});
        m.setTexture("atlas", this.atlasTex);
        m.setColor4("baseColor", new BABYLON.Color4(1, 1, 1, 1));
        m.setVector4("u_held", new BABYLON.Vector4(...this.held));
        m.backFaceCulling = false;
        const engine = this.engine, here = new BABYLON.Vector2(1, 0), flash = new BABYLON.Vector4(1, 0.15, 0.15, 0);
        const tint = new BABYLON.Vector3(1, 1, 1), white = new BABYLON.Vector3(1, 1, 1);
        m.onBindObservable.add(mesh => {
            // (each model's own light where it stands, and its red flash: craft_gfx.set_here, flash; a glowing part,
            // craft_models.glow: full light whatever light it stands in, its fog and hurt flash kept)
            const e = engine._currentEffect || m.getEffect();
            if (!e) return;
            const h = mesh && mesh.ccHere, lit = mesh && mesh.ccGlow, L = this.timeLook;
            here.set(lit ? 1 : h ? h[0] : 1, lit ? 0 : h ? h[1] : 0);
            flash.w = h && h[2] ? 0.55 : 0;
            e.setVector2("u_here", here);
            e.setVector4("u_flash", flash);
            e.setFloat("u_day", lit ? 1.0 : L ? L.daylight : 1.0);
            if (L && !lit) tint.set(L.tint[0], L.tint[1], L.tint[2]);
            e.setVector3("u_tint", lit || !L ? white : tint);
        });
        (this.shaded || (this.shaded = [])).push(m);
        return m;
    }

    // a flat colour material (the sky, the outline, the effects): opts {tex, vcol, stroke, add, point}; each mesh's
    // ccColour (or the material's) is the colour it is drawn in, a colour scale as the window's setColorScale
    flatMaterial(name, opts = {}) {
        const defines = [];
        if (opts.tex) defines.push("TEX");
        if (opts.vcol) defines.push("VCOL");
        if (opts.stroke) defines.push("STROKE");
        const attributes = ["position"];
        if (opts.tex || opts.stroke) attributes.push("uv");
        if (opts.vcol) attributes.push("color");
        const m = new BABYLON.ShaderMaterial(name, this.scene, {vertex: "craftFlat", fragment: "craftFlat"}, {
            attributes, uniforms: ["worldViewProjection", "u_colour", "u_point", "baseColor"],
            samplers: opts.tex ? ["tex"] : [], defines, needAlphaBlending: true});
        if (opts.tex) m.setTexture("tex", opts.tex);
        m.setColor4("baseColor", new BABYLON.Color4(1, 1, 1, 1));
        m.setVector4("u_colour", new BABYLON.Vector4(1, 1, 1, 1));
        m.setFloat("u_point", 1);
        m.backFaceCulling = false;
        m.disableDepthWrite = true;
        m.alphaMode = opts.add ? BABYLON.Constants.ALPHA_ADD : BABYLON.Constants.ALPHA_COMBINE;
        if (opts.point) m.pointsCloud = true;
        const engine = this.engine, colour = new BABYLON.Vector4(1, 1, 1, 1);
        m.onBindObservable.add(mesh => {
            const e = engine._currentEffect || m.getEffect();
            if (!e) return;
            const c = (mesh && mesh.ccColour) || m.ccColour || [1, 1, 1, 1];
            colour.set(c[0], c[1], c[2], c[3]);
            e.setVector4("u_colour", colour);
            e.setFloat("u_point", (mesh && mesh.ccPoint) || 1);
        });
        return m;
    }

    // a picture made here (pictureFn: sunPicture...) as a smooth texture (craft_gfx.image_texture)
    pictureTexture(name, n, fn, smooth = true) {
        const t = new BABYLON.RawTexture(picture(n, fn), n, n, BABYLON.Constants.TEXTUREFORMAT_RGBA, this.scene, smooth, false,
                                         smooth ? BABYLON.Constants.TEXTURE_TRILINEAR_SAMPLINGMODE : BABYLON.Constants.TEXTURE_NEAREST_SAMPLINGMODE);
        t.name = name;
        t.hasAlpha = true;
        t.wrapU = t.wrapV = BABYLON.Texture.CLAMP_ADDRESSMODE;
        return t;
    }

    // the sun's shadow (medium and up): a depth picture from the sun over the ground round you (craft_gfx.init)
    makeShadow(size) {
        const scene = this.scene, area = SHADOW_AREA[this.tier];
        const rtt = this.rtt = new BABYLON.RenderTargetTexture("shadow", {width: size, height: size}, scene,
            {generateMipMaps: false, generateDepthBuffer: true, noColorAttachment: true});
        rtt.createDepthStencilTexture(BABYLON.Constants.LEQUAL, true);
        const cam = this.sunCam = new BABYLON.FreeCamera("suncam", new BABYLON.Vector3(0, 100, 0), scene, false);
        cam.mode = BABYLON.Camera.ORTHOGRAPHIC_CAMERA;
        cam.orthoLeft = -area / 2; cam.orthoRight = area / 2; cam.orthoTop = area / 2; cam.orthoBottom = -area / 2;
        cam.minZ = 1; cam.maxZ = 240;
        rtt.activeCamera = cam;
        rtt.renderList = [];
        rtt.refreshRate = 1;
        this.depthMat = new BABYLON.ShaderMaterial("ccdepth", scene, {vertex: "craftDepth", fragment: "craftDepth"},
            {attributes: ["position", "uv"], uniforms: ["world", "viewProjection"], samplers: ["atlas"]});
        this.depthMat.setTexture("atlas", this.atlasTex);
        // (the window's shadow map holds the faces turned away from the sun, so a side in the sun's lee is lit by its
        // own face shading and only what stands between it and the sun shades it: the same here, the faces towards the
        // sun left out; the plants and leaves, two-sided in the window too, both sides)
        this.depthMat.backFaceCulling = true;
        this.depthMat.cullBackFaces = false;
        this.depthMat2 = new BABYLON.ShaderMaterial("ccdepth", scene, {vertex: "craftDepth", fragment: "craftDepth"},
            {attributes: ["position", "uv"], uniforms: ["world", "viewProjection"], samplers: ["atlas"]});
        this.depthMat2.setTexture("atlas", this.atlasTex);
        this.depthMat2.backFaceCulling = false;
        scene.customRenderTargets.push(rtt);
        this.shadowMatrix = BABYLON.Matrix.Identity();
        this.shadowArea = area;
    }

    // the sky (craft_gfx.Sky): a dome deepening to the zenith's colour overhead, the sun (a round disc in a soft glow,
    // a coral or amber halo round it at dusk and dawn) and the moon (round, opposite it) crossing it with the time of
    // day, the stars at night, behind everything and round the camera; the clouds (soft puffs at two heights,
    // drifting east, facing you) over the island round you
    makeSky() {
        const scene = this.scene, root = new BABYLON.TransformNode("sky", scene), S = skyData || {};
        // (inside the far plane on every tier, as the window's)
        const r = Math.min(250.0, this.camera.maxZ * 0.8), k = r / 250.0;
        const put = (m, order) => { m.parent = root; m.renderingGroupId = 0; m.alphaIndex = order; m.isPickable = false; return m; };
        // the dome: white, see-through at the horizon and solid overhead, in the zenith's colour (the time's)
        const rings = [0, 4, 9, 16, 25, 37, 52, 70, 90], seg = 24, pos = [], col = [], idx = [];
        for (const el of rings) {
            const e = el * DEG, a = smooth(Math.sin(e) / 0.75) ** 0.9, ce = Math.cos(e) * r;
            for (let i = 0; i <= seg; i++) {
                const az = i / seg * 2 * Math.PI;
                pos.push(ce * Math.cos(az), Math.sin(e) * r, ce * Math.sin(az));
                col.push(1, 1, 1, a);
            }
        }
        for (let q = 0; q < rings.length - 1; q++) for (let i = 0; i < seg; i++) {
            const p = q * (seg + 1) + i, o = (q + 1) * (seg + 1) + i;
            idx.push(p, p + 1, o + 1, p, o + 1, o);
        }
        const dome = new BABYLON.Mesh("dome", scene), dv = new BABYLON.VertexData();
        dv.positions = pos; dv.colors = col; dv.indices = idx;
        dv.applyToMesh(dome);
        dome.hasVertexAlpha = true;
        dome.material = this.flatMaterial("ccdome", {vcol: true});
        put(dome, 0);
        const halo = put(cardMesh(this, "halo", 95 * k, 95 * k, this.flatMaterial("cchalo", {tex: this.pictureTexture("halo", 64, dotPicture), add: true})), 1);
        halo.billboardMode = BABYLON.Mesh.BILLBOARDMODE_ALL;
        // the stars: craft_gfx's five hundred (craft.json's sky, as the window's numpy drew them), a few bigger
        const stars = [];
        for (const size of [1, 2]) {
            const list = (S.stars || []).filter(s => s[6] === size), sp = [], sc = [];
            for (const s of list) { sp.push(s[0] * r * 0.98, s[2] * r * 0.98, s[1] * r * 0.98); sc.push(s[3], s[4], s[5], 1); }
            if (!sp.length) continue;
            const m = new BABYLON.Mesh("stars", scene), vd = new BABYLON.VertexData();
            vd.positions = sp; vd.colors = sc; vd.indices = list.map((_, i) => i);
            vd.applyToMesh(m);
            m.material = this.flatMaterial("ccstars" + size, {vcol: true, point: true});
            m.ccSize = size;
            stars.push(put(m, 1));
        }
        const starNode = new BABYLON.TransformNode("starnode", scene);  // (one thing to switch on and off: the tests')
        starNode.parent = root;
        for (const m of stars) m.parent = starNode;
        const moon = put(cardMesh(this, "moon", 11 * k, 11 * k, this.flatMaterial("ccmoon", {tex: this.pictureTexture("moon", 128, moonPicture)})), 2);
        const sun = put(cardMesh(this, "sun", 18 * k, 18 * k, this.flatMaterial("ccsun", {tex: this.pictureTexture("sun", 128, sunPicture), add: true})), 3);
        for (const m of [moon, sun]) m.billboardMode = BABYLON.Mesh.BILLBOARDMODE_ALL;
        // the clouds: tex/craft_clouds.png (craft_gfx.cloud_image's four), where each starts as the window's draws
        const clouds = [], n = CLOUDS[this.tier] || 0, C = S.clouds || {}, span = Math.max(60.0, this.camera.maxZ * 0.72);
        const layout = (C.layouts || {})[String(n)] || [];
        if (n && layout.length) {
            const tex = new BABYLON.Texture(C.file || "tex/craft_clouds.png", scene, false, true, BABYLON.Constants.TEXTURE_TRILINEAR_SAMPLINGMODE);
            tex.hasAlpha = true;
            tex.wrapU = tex.wrapV = BABYLON.Texture.CLAMP_ADDRESSMODE;
            const mat = this.flatMaterial("ccclouds", {tex}), aspect = C.aspect || 3.0, e = 0.5 / 512;
            for (const [w, pic, dx, dy, layer] of layout) {
                const m = cardMesh(this, "cloud", w, w / aspect, mat, [0, 1 - (pic + 1) / 4 + e, 1, 1 - pic / 4 - e]);
                m.billboardMode = BABYLON.Mesh.BILLBOARDMODE_ALL;
                m.renderingGroupId = 1;
                m.alphaIndex = 100;
                clouds.push({m, x: -span + 2 * span * dx, y: -span + 2 * span * dy, layer, w});
            }
        }
        return {root, dome, halo, stars: starNode, starMeshes: stars, moon, sun, clouds, drift: 0, span, r,
                colour: [1, 1, 1]};
    }

    // the sky's look at the time (craft_gfx.Sky.update): where the sun and moon are, how bright, the stars, the
    // clouds' colour
    skyLook(L) {
        const S = this.sky, d = L.sunDir, r = S.r;
        const at = f => v3(d[0] * r * f, d[1] * r * f, d[2] * r * f);
        S.sun.position = at(0.9);
        S.moon.position = v3(-d[0] * r * 0.9, -d[1] * r * 0.9, -d[2] * r * 0.9);
        S.dome.ccColour = [...L.zenith, 1];
        const glow = Math.max(smooth(L.dusk), smooth(L.dawn));
        S.halo.position = at(0.88);
        const hc = L.dusk >= L.dawn ? SKY_DUSK : SKY_DAWN;
        S.halo.ccColour = [hc[0], hc[1], hc[2], 0.55 * glow];
        S.halo.setEnabled(glow > 0.01);
        const up = clamp((d[2] + 0.06) * 8, 0, 1), low = clamp(d[2] * 3, 0, 1);  // (low in the sky: warmer)
        S.sun.ccColour = [1.0, 0.72 + 0.28 * low, 0.5 + 0.5 * low, up];
        S.sun.setEnabled(up > 0.01);
        const mup = clamp((-d[2] + 0.06) * 8, 0, 1) * (0.35 + 0.65 * (1 - L.day));
        S.moon.ccColour = [1, 1, 1, mup];
        S.moon.setEnabled(mup > 0.01);
        const night = Math.max(0, 1 - L.day * 1.6);
        for (const m of S.starMeshes) m.ccColour = [1, 1, 1, night];
        S.stars.setEnabled(night > 0.02);
        let c = mix3([0.16, 0.2, 0.32], [1, 1, 1], L.day);
        c = mix3(c, [1.0, 0.62, 0.72], smooth(L.dusk) * 0.55);
        c = mix3(c, [1.0, 0.8, 0.6], smooth(L.dawn) * 0.5);
        S.colour = c;
    }

    // the clouds drift east and wrap round the camera, fading out at the edge of the sky they fill (Sky.follow)
    cloudsFollow(cam, dt) {
        const S = this.sky;
        if (!S || !S.clouds.length || !cam) return;
        S.drift += dt * 1.2;
        const span = S.span, mod = (a, b) => ((a % b) + b) % b;
        const baseZ = Math.max(78.0, this.world ? this.world.Z + 12.0 : 78.0);
        for (const c of S.clouds) {
            const speed = 1.0 + c.layer * 0.5;
            const dx = mod(c.x + S.drift * speed - cam[0] + span, 2 * span) - span;
            const dy = mod(c.y - cam[1] + span, 2 * span) - span;
            const a = clamp((span - Math.hypot(dx, dy)) / (span * 0.35), 0, 1);
            if (a <= 0.01) { c.m.setEnabled(false); continue; }
            c.m.setEnabled(true);
            c.m.position = v3(cam[0] + dx, cam[1] + dy, baseZ + c.layer * 16);
            c.m.ccColour = [S.colour[0], S.colour[1], S.colour[2], a * (c.layer === 0 ? 0.95 : 0.75)];
        }
    }

    // the block you look at (craft_gfx.Target): a cyan glow outline round it (2 pixels, a 6 pixel glow, breathing
    // gently), fitted to the block's shape; as you dig its faces dissolve pixel by pixel to the night navy (u_dig in
    // the blocks' shader; on the looks a 16 x 16 mask over the block in the line colour)
    makeTarget() {
        const mat = this.flatMaterial("cctarget", {vcol: true, stroke: true});
        const glow = new Strokes(this, "target glow", 12, mat, 300), core = new Strokes(this, "target", 12, mat, 301);
        for (const [s, w] of [[glow, 6.0], [core, 2.0]]) for (const seg of s.segs) { seg.w = w; seg.ca = seg.cb = [...CYAN, 1]; }
        glow.mesh.setEnabled(false);
        core.mesh.setEnabled(false);
        let mask = null;
        if (this.wire) {
            const g = {pos: [], uv: [], idx: []};
            for (let d = 0; d < 6; d++) {
                const n = g.pos.length / 3;
                CORNERS[d].forEach((c, q) => { g.pos.push(c[0], c[2], c[1]); g.uv.push(UV[q][0], UV[q][1]); });
                g.idx.push(n, n + 1, n + 2, n, n + 2, n + 3);
            }
            mask = new BABYLON.Mesh("dig mask", this.scene);
            const vd = new BABYLON.VertexData();
            vd.positions = g.pos; vd.uvs = g.uv; vd.indices = g.idx;
            vd.applyToMesh(mask);
            this.maskPixels = new Uint8Array(16 * 16 * 4);
            this.maskTex = new BABYLON.RawTexture(this.maskPixels, 16, 16, BABYLON.Constants.TEXTUREFORMAT_RGBA, this.scene, false, false,
                                                  BABYLON.Constants.TEXTURE_NEAREST_SAMPLINGMODE);
            this.maskTex.hasAlpha = true;
            const m = this.flatMaterial("ccdigmask", {tex: this.maskTex});
            m.zOffset = -2;
            mask.material = m;
            mask.renderingGroupId = 1;
            mask.alphaIndex = 299;
            mask.isPickable = false;
            mask.ccColour = [1, 1, 1, 1];
            mask.setEnabled(false);
        }
        const order = (skyData && skyData.dig_order) || Array.from({length: 256}, (_, i) => mulberry(7 + i)());
        return {glow, core, mask, order, block: null, stage: null, lo: [0, 0, 0], size: [1, 1, 1]};
    }

    // the box the outline goes round: the block's own shape (a step half high, a glowstick thin), as [lo, hi] in the
    // block (craft_gfx.block_bounds)
    blockBounds(x, y, z) {
        const w = this.world, full = [[0, 0, 0], [1, 1, 1]];
        if (!w || !w.inside(x, y, z)) return full;
        const b = sim.B.blocks[w.get(x, y, z)], meta = w.getMeta(x, y, z);
        const shape = b && b.shape;
        if (shape === "slab") return [[0, 0, 0], [1, 1, 0.5]];
        if (shape === "bed") return [[0, 0, 0], [1, 1, 0.6]];
        if (shape === "farmland") return [[0, 0, 0], [1, 1, 0.875]];
        if (shape === "torch") return [[0.38, 0.38, 0], [0.62, 0.62, 0.7]];
        if (shape === "cross") return [[0.15, 0.15, 0], [0.85, 0.85, 0.95]];
        if (shape === "crop") return [[0, 0, 0], [1, 1, 0.9]];
        if (shape === "ladder") {
            const face = meta % 4;
            return [[[0.9, 0, 0], [0, 0, 0], [0, 0.9, 0], [0, 0, 0]][face], [[1, 1, 1], [0.1, 1, 1], [1, 1, 1], [1, 0.1, 1]][face]];
        }
        if (shape === "door") {
            const side = ((meta & 3) + (meta & 4 ? 1 : 0)) % 4;
            return [[[0, 0, 0], [0.19, 1, 1]], [[0, 0.81, 0], [1, 1, 1]], [[0.81, 0, 0], [1, 1, 1]], [[0, 0, 0], [1, 0.19, 1]]][side];
        }
        return full;
    }

    setDig(value) {  // (u_dig on the blocks' materials, in Babylon's axes)
        const v = [value[0], value[2], value[1], value[3]];
        if (v.join() === this.dig.join()) return;
        this.dig = v;
        const V = new BABYLON.Vector4(...v);
        for (const m of this.shaded || []) if (m.ccChunk) m.setVector4("u_dig", V);
    }

    // block: [x, y, z] or null; progress: the dig, 0 to 1. Called every frame (the outline breathes)
    showTarget(block, progress) {
        const T = this.target;
        if (!T) return;
        if (!block) {
            T.glow.mesh.setEnabled(false);
            T.core.mesh.setEnabled(false);
            T.block = null;
            if (T.mask) T.mask.setEnabled(false);
            else this.setDig([0, 0, -1000, 0]);
            return;
        }
        const [bx, by, bz] = block.map(v => Math.floor(v)), key = `${bx},${by},${bz}`;
        // (again where the block changes, or its shape does: a door opened, a step put down)
        const [lo, hi] = this.blockBounds(bx, by, bz), shape = lo.join() + hi.join();
        if (T.block !== key || T.shape !== shape) {
            T.block = key;
            T.shape = shape;
            const e = 0.004;
            T.lo = [bx + lo[0] - e, by + lo[1] - e, bz + lo[2] - e];
            T.size = [hi[0] - lo[0] + 2 * e, hi[1] - lo[1] + 2 * e, hi[2] - lo[2] + 2 * e];
            for (const s of [T.glow, T.core]) s.segs.forEach((seg, i) => {
                const [p, q] = BOX_EDGES[i];
                seg.a = p.map((v, j) => T.lo[j] + v * T.size[j]);
                seg.b = q.map((v, j) => T.lo[j] + v * T.size[j]);
            });
        }
        T.glow.mesh.setEnabled(true);
        T.core.mesh.setEnabled(true);
        const now = performance.now() / 1000, breath = 0.5 + 0.5 * Math.sin(now * 1.1 * 2 * Math.PI);
        T.core.mesh.ccColour = [1, 1, 1, 0.75 + 0.25 * breath];
        T.glow.mesh.ccColour = [1, 1, 1, 0.22 + 0.22 * breath];
        progress = clamp(Number(progress) || 0, 0, 1);
        if (!T.mask) {
            this.setDig([bx, by, bz, progress > 0 ? progress * 0.97 : 0]);
            return;
        }
        if (progress <= 0) { T.mask.setEnabled(false); return; }
        T.mask.position = v3(...T.lo);
        T.mask.scaling = new BABYLON.Vector3(T.size[0], T.size[2], T.size[1]);
        T.mask.setEnabled(true);
        const stage = `${Math.floor(progress * 32)},${Math.floor(now * 10)}`;
        if (stage === T.stage) return;
        T.stage = stage;
        const c = BABYLON.Color3.FromHexString(getLineColour()), blink = mulberry(Math.floor(now * 10) + 1);
        // (the mask's rows: the window's top row is its picture's top, the texture's first row its bottom)
        for (let row = 0; row < 16; row++) for (let col = 0; col < 16; col++) {
            const o = T.order[(15 - row) * 16 + col], gone = o < progress * 0.97;
            const blinks = !gone && o < progress + 0.12 && blink() > 0.55, i = (row * 16 + col) * 4;
            this.maskPixels[i] = c.r * 255; this.maskPixels[i + 1] = c.g * 255; this.maskPixels[i + 2] = c.b * 255;
            this.maskPixels[i + 3] = gone ? 255 : blinks ? 128 : 0;
        }
        this.maskTex.update(this.maskPixels);
    }

    // a light carried (a Glowfruit held: level 6; craft_gfx.set_held_light): the blocks, the creatures and the hand
    // near pos (the eye, in the game's axes) lit as block light a level less a block from it; level 0: none
    setHeldLight(level, pos = null) {
        if (this.wire || !this.mats) return;
        level = clamp(Number(level) || 0, 0, sim.B.lightMax || 12);
        const v = level <= 0 || !pos ? [0, -1000, 0, 0] : [pos[0], pos[2], pos[1], level];
        if (v.join() === this.held.join()) return;
        this.held = v;
        const V = new BABYLON.Vector4(...v);
        for (const m of this.shaded || []) m.setVector4("u_held", V);
    }

    // ---------- the time of day (craft_gfx.set_time) ----------
    setTime(t) {
        if (Math.abs(t - this.time) < 0.0005 && this.timeLook) return;
        this.time = ((t % 1) + 1) % 1;
        this.applyTime();
    }

    applyTime() {
        const L = this.timeLook = timeLook(this.time);
        if (!this.scene) return;
        if (!this.wire) this.scene.clearColor = new BABYLON.Color4(L.sky[0], L.sky[1], L.sky[2], 1);
        const v = this.view();
        for (const m of this.shaded || []) {
            m.setFloat("u_day", L.daylight);
            m.setVector3("u_tint", new BABYLON.Vector3(...L.tint));
            m.setVector3("u_fog_colour", new BABYLON.Vector3(...L.sky));
            m.setVector2("u_fog", new BABYLON.Vector2(v * 0.62, v * 0.98));
            if (m.ccChunk) m.setFloat("u_wave", WAVES.has(this.tier) ? 1 : 0);
        }
        if (this.sky) this.skyLook(L);
    }

    // ---------- every frame ----------
    // the shaders' clock (waving leaves, animated tiles, the dig's blinking pixels), the sun's shadow over the camera,
    // the sky round it, the clouds drifting, the effects (craft_gfx.tick, Effects.update)
    tick(dt, cam) {
        this.waveT += dt;
        for (const m of this.shaded || []) if (m.ccChunk) m.setFloat("u_time", this.waveT % 3600.0);
        const camB = this.camera.position;
        if (this.sky) {
            this.sky.root.position.copyFrom(camB);
            this.cloudsFollow(cam, dt);
        }
        if (this.effects) this.effects.update(dt);
        if (this.rtt && this.timeLook) {
            let d = this.timeLook.sunDir;
            if (d[2] < 0.05) d = d.map(v => -v);  // (the sun below the horizon: the moon's light, from above)
            const target = new BABYLON.Vector3(cam[0], cam[2], cam[1]);
            this.sunCam.position = target.add(new BABYLON.Vector3(d[0] * 120, d[2] * 120, d[1] * 120));
            this.sunCam.setTarget(target);
            this.sunCam.computeWorldMatrix(true);
            this.shadowMatrix.copyFrom(this.sunCam.getViewMatrix(true).multiply(this.sunCam.getProjectionMatrix(true)));
            for (const m of this.shaded || []) if (m.ccChunk) m.setMatrix("shadowMatrix", this.shadowMatrix);
            // (what casts: the chunks round you, the players and creatures)
            const r = this.shadowArea / 2 + CHUNK * 1.5, list = [];
            for (const [key, ch] of this.chunks) {
                if (Math.hypot(ch.cx - cam[0], ch.cy - cam[1]) < r) for (const m of ch.casters) list.push(m);
            }
            for (const md of this.models.values()) for (const m of md.meshes) if (!m.isDisposed()) list.push(m);
            this.rtt.renderList = list;
            for (const m of list) {
                if (m.ccDepth) continue;
                this.rtt.setMaterialForRendering(m, m.ccPass === 1 ? this.depthMat2 : this.depthMat);
                m.ccDepth = true;
            }
        }
    }

    // just before each picture: the outline's and the effects' lines turned to where the camera is now
    beforeRender() {
        const T = this.target;
        if (T && T.core.mesh.isEnabled()) { T.glow.commit(); T.core.commit(); }
        if (this.effects) this.effects.commit();
        if (this.sky) {  // (the stars' points: 1 and 2 window pixels, thicker on a bigger window: craft_gfx.line_px)
            const eng = this.engine, rh = eng.getRenderHeight();
            const css = (eng.getRenderingCanvas() && eng.getRenderingCanvas().clientHeight) || rh;
            for (const m of this.sky.starMeshes) m.ccPoint = m.ccSize * Math.max(1, css / 720) * rh / css;
        }
    }

    // the chunks changed since last time and those not yet drawn, nearest the camera first, for up to budget ms
    // (everything in reach the first time) (craft_gfx.WorldVisual.update)
    updateChunks(cx, cy, budget = 8, first = false) {
        const w = this.world;
        if (!w || !this.mats) return 0;
        for (const k of w.dirty) this.todo.add(k);
        w.dirty.clear();
        const reach = this.view() + CHUNK;
        let n = 0;
        if (this.todo.size) {
            const order = [...this.todo].map(k => {
                const [a, b] = k.split(",").map(Number);
                return [k, a, b, (a * CHUNK + 8 - cx) ** 2 + (b * CHUNK + 8 - cy) ** 2];
            }).sort((p, q) => p[3] - q[3]);
            const t0 = performance.now();
            for (const [key, a, b, d2] of order) {
                const far = Math.sqrt(d2) > reach;
                if (far && !this.chunks.has(key)) continue;  // (out of view: drawn when you come near)
                this.todo.delete(key);
                this.rebuild(key, a, b);
                n++;
                if (!first && performance.now() - t0 > budget) break;
            }
        }
        // chunks further than the view hidden (the fog has them anyway)
        const hide = this.view() + CHUNK * 1.5;
        for (const ch of this.chunks.values()) {
            const on = Math.hypot(ch.cx - cx, ch.cy - cy) <= hide;
            if (ch.on !== on) { ch.on = on; for (const m of ch.meshes) m.setEnabled(on); }
        }
        return n;
    }

    rebuild(key, cx, cy) {
        const old = this.chunks.get(key);
        if (old) for (const m of old.meshes) m.dispose();
        const look = this.lineLook(), out = meshChunk(this.world, cx, cy, this.tables, look);
        const meshes = [], casters = [], scene = this.scene, engine = this.engine;
        out.passes.forEach((a, p) => {
            if (!a) return;
            const n = a.pos.length / 3, pos = new Float32Array(n * 3), idx = new Uint32Array(a.idx.length);
            for (let i = 0; i < n; i++) { pos[i * 3] = a.pos[i * 3]; pos[i * 3 + 1] = a.pos[i * 3 + 2]; pos[i * 3 + 2] = a.pos[i * 3 + 1]; }
            idx.set(a.idx);  // (the window's winding: with y and z swapped Babylon sees it as its own front)
            const m = new BABYLON.Mesh(`chunk ${key} ${p}`, scene);
            m.setVerticesData(BABYLON.VertexBuffer.PositionKind, pos, false, 3);
            m.setVerticesData(BABYLON.VertexBuffer.UVKind, a.uv, false, 2);
            if (!look) m.setVerticesBuffer(new BABYLON.VertexBuffer(engine, a.c, "cdata", {updatable: false, stride: 4, size: 4,
                                                                                               type: BABYLON.VertexBuffer.UNSIGNED_BYTE, normalized: true}));
            m.setIndices(idx, n);
            m.material = [this.mats.solid, this.mats.cutout, this.mats.blend][p];
            m.renderingGroupId = 1;
            m.isPickable = false;
            m.parent = this.chunkRoot;
            m.freezeWorldMatrix();
            m.ccPass = p;
            if (p === 2) m.alphaIndex = 50;
            meshes.push(m);
            if (p < 2) casters.push(m);
        });
        if (look && out.lines && out.lines.length) {
            const L = out.lines, n = L.length / 3, pos = new Float32Array(n * 3);
            for (let i = 0; i < n; i++) { pos[i * 3] = L[i * 3]; pos[i * 3 + 1] = L[i * 3 + 2]; pos[i * 3 + 2] = L[i * 3 + 1]; }
            const ln = this.linesMesh(`chunklines ${key}`, {pos, idx: Array.from({length: n}, (_, i) => i)}, this.mats.lines);
            if (ln) { ln.renderingGroupId = 1; meshes.push(ln); }
        }
        this.chunks.set(key, {meshes, casters, cx: cx * CHUNK + 8, cy: cy * CHUNK + 8, on: true});
        this.built++;
    }

    // ---------- particles (craft_gfx.Particles): small squares of the block's own texture, falling ----------
    burst(x, y, z, tile, n = null, speed = 2.5) {
        if (!this.atlas || !this.mats) return;
        n = n || PARTICLES[this.tier] || 12;
        const [u0, v0, s] = uvOf(this.atlas.where, this.atlas.where[tile] ? tile : "particle"), rnd = Math.random;
        for (let i = 0; i < n; i++) {
            const q = s / 4, cu = u0 + rnd() * (s - q), cv = v0 + rnd() * (s - q);
            const g = boxGeo({}, [[[-0.05, -0.05, -0.05], [0.05, 0.05, 0.05], "particle", [1, 1, 1]]]);
            for (let k = 0; k < g.uv.length; k += 2) { g.uv[k] = cu + UV[(k / 2) % 4][0] * q; g.uv[k + 1] = cv + UV[(k / 2) % 4][1] * q; }
            const m = this.geoMesh("bit", g, this.particleMat);
            m.position = v3(x + rnd() * 0.6 + 0.2, y + rnd() * 0.6 + 0.2, z + rnd() * 0.6 + 0.2);
            const vel = [(rnd() - 0.5) * speed, (rnd() - 0.5) * speed, Math.abs((rnd() - 0.5) * speed) + 1.5];
            m.ccHere = this.hereAt(x + 0.5, y + 0.5, z + 0.5);
            this.bits.push({m, vel, life: 0.6 + rnd() * 0.5});
        }
    }

    updateBits(dt) {
        const keep = [];
        for (const b of this.bits) {
            b.life -= dt;
            if (b.life <= 0) { b.m.dispose(); continue; }
            b.vel[2] -= 18 * dt;
            b.m.position.x += b.vel[0] * dt;
            b.m.position.z += b.vel[1] * dt;
            b.m.position.y += b.vel[2] * dt;
            keep.push(b);
        }
        this.bits = keep;
    }

    // a geometry (boxGeo's) as a mesh in material mat, drawn with the world
    geoMesh(name, g, mat, parent = null) {
        const m = new BABYLON.Mesh(name, this.scene), vd = new BABYLON.VertexData();
        vd.positions = g.pos;
        vd.uvs = g.uv;
        vd.colors = g.col;
        vd.indices = g.idx;
        vd.applyToMesh(m);
        m.material = mat;
        m.isPickable = false;
        m.renderingGroupId = 1;
        if (parent) m.parent = parent;
        return m;
    }

    // a model's part: its mesh and, on the line tiers, its edges in the line colour (line_look.outline)
    part(name, g, parent, holder) {
        const m = this.geoMesh(name, g, this.mats.ent, parent);
        holder.meshes.push(m);
        if (this.wire) {
            const ln = this.linesMesh(name + " lines", this.edgeLines([m], this.wire, m), this.mats.entLines, m);
            if (ln) { ln.renderingGroupId = m.renderingGroupId; holder.lines.push(ln); }
        }
        return m;
    }

    // the light where a thing stands: the sky's and the glowsticks' (0 to 1: the level over the full light), and
    // whether it flashes (craft_gfx.set_here)
    hereAt(x, y, z) {
        const w = this.world, L = sim.B.lightMax || 12;
        const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z + 0.5);
        if (!w || !w.inside(xi, yi, zi)) return [1, 0, 0];
        const i = w.at(xi, yi, zi);
        return [w.sky[i] / L, w.glow[i] / L, 0];
    }

    drawCalls() { return this.scene ? this.scene.getActiveMeshes().length : 0; }

    stats() {  // (the tests and the Graphics tab)
        let meshes = 0, lines = 0;
        for (const ch of this.chunks.values()) for (const m of ch.meshes) (m.material && m.material.ccLine ? lines++ : meshes++);
        return {chunks: this.chunks.size, todo: this.todo.size, meshes, lines, models: this.models.size, built: this.built};
    }
}

// ---------- people, creatures and Craft Bots (craft_models.py) ----------
// - a player: a Club Coder in a lab suit in their profile's colour, a big rounded head, a cyan visor across the eyes
//   that glows in the dark, a backpack, short arms, chunky boots; the suit pieces they wear (visor, vest, boots)
// - a Fluff: a round floating puff with big eyes on two tiny feet, bobbing; brushed (F_SLEEP), a smaller puff
// - a Glitch: a flickering cluster of magenta and cyan pixels that keeps changing shape, two bright eyes
// - a Rust Walker: an old tracked robot, rust on a navy shell, coral eyes, a long magnet arm that swings to grab
// - a Bleep and a Craft Bot: Club Coders' own robots (the Bot wears the club's mark on its chest)
const WHITE = [1, 1, 1];
const faces = (front, other) => [other, other, front, other, other, other];
const rgb01 = c => (c && c.length >= 3 ? c.slice(0, 3).map(v => clamp(v / 255, 0, 1)) : [0.9, 0.9, 0.9]);

// a box with its edges taken off: three boxes, each a little short on two axes (a head, a puff of fluff)
function rounded(lo, hi, cut, tiles, colour) {
    const [x0, y0, z0] = lo, [x1, y1, z1] = hi;
    return [[[x0, y0 + cut, z0 + cut], [x1, y1 - cut, z1 - cut], tiles, colour],
            [[x0 + cut, y0, z0 + cut], [x1 - cut, y1, z1 - cut], tiles, colour],
            [[x0 + cut * 0.9, y0 + cut * 0.9, z0], [x1 - cut * 0.9, y1 - cut * 0.9, z1], tiles, colour]];
}

export class Model {
    static VOXEL = 0.2;

    constructor(sc, kind, colour, name) {
        this.sc = sc;
        this.kind = kind;
        this.meshes = [];
        this.lines = [];
        const scene = sc.scene;
        this.root = new BABYLON.TransformNode(`${kind} model`, scene);
        this.body = new BABYLON.TransformNode("body", scene);
        this.body.parent = this.root;
        this.legs = [];
        this.arms = [];
        this.head = null;
        this.phase = 0;
        this.swing = 0;
        this.t = 0;
        this.here = [1, 0, 0];
        this.worn = [0, 0, 0];
        this.suit = [];
        const c = rgb01(colour);
        const build = {player: this.buildPlayer, fluff: this.buildFluff, glitch: this.buildGlitch, rust: this.buildRust,
                       bleep: this.buildBleep, bot: this.buildBot}[kind] || this.buildPlayer;
        build.call(this, c);
        this.tag = null;
        this.name = name;
        if (name) this.makeTag(name);
    }

    node(parent, pivot, name = "joint") {
        const n = new BABYLON.TransformNode(name, this.sc.scene);
        n.parent = parent;
        n.position = v3(...pivot);
        return n;
    }

    // boxes [[lo, hi, tiles, colour]] as one mesh under parent (craft_gfx.model); glow: it shines in the dark
    model(parent, parts, glow = false) {
        const m = this.sc.part(this.kind, boxGeo(this.sc.atlas.where, parts), parent, this);
        m.ccHere = this.here;
        if (glow) m.ccGlow = true;
        return m;
    }

    limb(parent, pivot, parts) {  // a part that swings about pivot: its boxes hang from it
        const j = this.node(parent, pivot);
        this.model(j, parts);
        return j;
    }

    shine(parent, parts, name = "glow") {  // a part that shines in the dark (craft_models.glow)
        const n = this.node(parent, [0, 0, 0], name);
        this.model(n, parts, true);
        return n;
    }

    // a Club Coder: 0.7 wide and 1.7 tall (craft_sim's box), eyes at 1.55: legs to 0.55, the suit to 1.1, the head to 1.7
    buildPlayer(c) {
        const suit = c;
        this.legs = [-0.13, 0.13].map(x => this.limb(this.body, [x, 0, 0.55], [
            [[-0.11, -0.11, -0.4], [0.11, 0.11, 0], "suit", suit],
            [[-0.14, -0.16, -0.55], [0.14, 0.21, -0.37], "boot", WHITE]]));
        this.model(this.body, [
            [[-0.25, -0.15, 0.53], [0.25, 0.15, 1.1], ["suit", "suit", "suit_front", "suit", "suit", "suit"], suit],
            [[-0.26, -0.16, 0.55], [0.26, 0.16, 0.64], ["glove", "glove", "belt", "glove", "glove", "glove"], WHITE],
            [[0.06, 0.15, 0.88], [0.18, 0.162, 1.0], "logo_mark", WHITE],  // (the club's badge)
            [[-0.18, -0.29, 0.66], [0.18, -0.15, 1.06], "backpack", WHITE]]);
        this.arms = [-0.335, 0.335].map(x => this.limb(this.body, [x, 0, 1.06], [
            [[-0.085, -0.085, -0.31], [0.085, 0.085, 0.03], "suit", suit],
            [[-0.095, -0.095, -0.43], [0.095, 0.095, -0.31], "glove", WHITE]]));
        this.head = this.node(this.body, [0, 0, 1.1], "head");
        const side = "coder_side", face = "coder_face", hair = "coder_hair", skin = "skin";
        this.model(this.head, [
            [[-0.30, -0.25, 0.05], [0.30, 0.25, 0.55], [side, side, side, hair, hair, skin], WHITE],
            [[-0.25, -0.30, 0.05], [0.25, 0.30, 0.55], [side, side, face, hair, hair, skin], WHITE],
            [[-0.255, -0.255, 0.0], [0.255, 0.255, 0.6], [side, side, face, hair, hair, skin], WHITE]]);
        this.visor = this.shine(this.head, [[[-0.31, 0.0, 0.28], [0.31, 0.32, 0.41], "visor_glow", WHITE]], "visor");
    }

    // (craft_models.Model.wear) dress a Club Coder in the suit pieces worn (three item ids: visor, vest, boots; 0 for
    // nothing), in their material, a little bigger than the parts they cover
    wear(ids) {
        ids = [...(ids || []), 0, 0, 0].slice(0, 3).map(v => Number(v) | 0);
        if (this.kind !== "player" || ids.join() === this.worn.join()) return;
        this.worn = ids;
        for (const n of this.suit) n.dispose();
        this.suit = [];
        const piece = (parent, parts) => {
            const n = this.node(parent, [0, 0, 0], "suit piece");
            this.model(n, parts);
            this.suit.push(n);
        };
        ids.forEach((id, part) => {
            const it = sim.B.items.get(id);
            if (!it || it.suit !== part) return;
            const tile = SUIT_TILES[it.key.split("_")[0]] || "iron_block";
            if (part === 0) {  // the visor: a frame round the glowing band, ear pieces and a crest
                piece(this.head, [[[-0.33, 0.0, 0.41], [0.33, 0.34, 0.46], tile, WHITE],
                                  [[-0.33, 0.0, 0.23], [0.33, 0.34, 0.28], tile, WHITE],
                                  [[-0.34, -0.09, 0.18], [0.34, 0.09, 0.46], tile, WHITE],
                                  [[-0.07, -0.33, 0.57], [0.07, 0.2, 0.67], tile, WHITE]]);
            } else if (part === 1) {  // the vest over the suit, pads on the shoulders, the badge on top
                piece(this.body, [[[-0.28, -0.18, 0.66], [0.28, 0.18, 1.12], tile, WHITE],
                                  [[0.06, 0.18, 0.88], [0.18, 0.192, 1.0], "logo_mark", WHITE]]);
                for (const arm of this.arms) piece(arm, [[[-0.105, -0.105, -0.12], [0.105, 0.105, 0.06], tile, WHITE]]);
            } else {  // the boots, over the boots
                for (const leg of this.legs) piece(leg, [[[-0.16, -0.18, -0.56], [0.16, 0.23, -0.34], tile, WHITE]]);
            }
        });
        this.meshes = this.meshes.filter(m => !m.isDisposed());
        this.lines = this.lines.filter(m => !m.isDisposed());
    }

    buildFluff() {
        this.legs = [-0.14, 0.14].map(x => this.limb(this.body, [x, 0, 0.26], [
            [[-0.03, -0.03, -0.22], [0.03, 0.03, 0.02], "fluff_foot", WHITE],
            [[-0.06, -0.05, -0.26], [0.06, 0.13, -0.2], "fluff_foot", WHITE]]));
        this.puff = this.node(this.body, [0, 0, 0.6], "puff");
        const tiles = ["fluff_white", "fluff_white", "fluff_face", "fluff_white", "fluff_white", "fluff_white"];
        this.model(this.puff, [...rounded([-0.4, -0.4, -0.36], [0.4, 0.4, 0.36], 0.08, tiles, WHITE),
                               [[-0.12, -0.14, 0.33], [0.12, 0.1, 0.44], "fluff_white", WHITE],
                               [[-0.46, -0.1, -0.06], [-0.38, 0.1, 0.12], "fluff_white", WHITE],
                               [[0.38, -0.1, -0.06], [0.46, 0.1, 0.12], "fluff_white", WHITE]]);
    }

    // a cluster of pixels (small cubes), magenta and cyan, that changes shape; two bright eyes in front
    buildGlitch() {
        const v = Model.VOXEL;
        this.cells = [];
        for (const x of [-1, 0, 1]) for (const y of [-1, 0, 1]) for (const z of [-1, 0, 1]) this.cells.push([x, y, z]);
        this.cells.push([-2, 0, 0], [2, 0, 0], [0, 0, 2], [0, 0, -2], [0, -2, 0], [-2, 0, 1], [2, 0, -1], [1, -2, 1]);
        this.cluster = this.node(this.body, [0, 0, 0.55], "cluster");
        this.voxels = [];
        for (let k = 0; k < 19; k++) {
            const n = this.node(this.cluster, [0, 0, 0], "pixel");
            this.model(n, [[[-v / 2, -v / 2, -v / 2], [v / 2, v / 2, v / 2], k % 3 === 0 ? "glitch_cyan" : "glitch_body", WHITE]], true);
            this.voxels.push(n);  // (a Glitch is a bug of light: it shows in the dark)
        }
        this.eyes = this.shine(this.cluster, [[[-0.17, 0.3, 0.04], [-0.05, 0.36, 0.16], "glitch_eye", WHITE],
                                              [[0.05, 0.3, 0.04], [0.17, 0.36, 0.16], "glitch_eye", WHITE]], "eyes");
        this.nextShape = 0;
        this.reshape();
    }

    // a new shape: most of the cluster's middle, a few pixels further out, one or two jumped sideways
    reshape() {
        const v = Model.VOXEL, r = Math.random, pick = (list, n) => {
            const a = [...list];
            for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
            return a.slice(0, n);
        };
        const side = () => (r() < 0.5 ? -1 : 1);
        const inner = this.cells.filter(p => Math.max(...p.map(Math.abs)) <= 1);
        const outer = this.cells.filter(p => Math.max(...p.map(Math.abs)) > 1);
        const picked = [...pick(inner, 15), ...pick(outer, 4)];
        this.voxels.forEach((n, i) => {
            const [x, y, z] = picked[i], jump = r() < 0.12 ? v * 0.5 : 0;
            n.position = v3(x * v + jump * side(), Math.min(1, y) * v, z * v);
            n.setEnabled(r() < 0.92);
        });
        this.cluster.position.x = v * 0.25 * [-1, 0, 0, 0, 1][Math.floor(r() * 5)];
        this.eyes.position.x = 0.02 * [-1, 0, 1][Math.floor(r() * 3)];
    }

    // a Rust Walker: two tracks, a navy hull with rust on it, a head with coral eyes, a long magnet arm
    buildRust() {
        const tr = ["track", "track", "tread", "tread", "tread", "tread"];
        this.model(this.body, [[[-0.38, -0.42, 0.0], [-0.16, 0.42, 0.3], tr, WHITE],
                               [[0.16, -0.42, 0.0], [0.38, 0.42, 0.3], tr, WHITE],
                               [[-0.16, -0.3, 0.08], [0.16, 0.3, 0.3], "metal_dark", WHITE]]);
        this.hull = this.node(this.body, [0, 0, 0], "hull");
        this.model(this.hull, [[[-0.3, -0.3, 0.3], [0.3, 0.3, 0.98], "rust_body", WHITE],
                               [[-0.24, 0.3, 0.45], [0.24, 0.33, 0.8], "metal_dark", WHITE],
                               [[-0.06, -0.06, 0.98], [0.06, 0.06, 1.08], "metal_dark", WHITE],
                               [[-0.4, -0.06, 0.62], [-0.3, 0.06, 0.88], "rust_body", WHITE]]);
        this.head = this.node(this.hull, [0, 0.04, 1.08], "head");
        this.model(this.head, [[[-0.2, -0.18, 0], [0.2, 0.2, 0.32], faces("rust_face", "rust_body"), WHITE],
                               [[0.09, -0.11, 0.32], [0.12, -0.08, 0.5], "metal_dark", WHITE]]);
        this.shine(this.head, [[[-0.15, 0.2, 0.18], [-0.05, 0.225, 0.26], "eye_coral", WHITE],
                               [[0.05, 0.2, 0.18], [0.15, 0.225, 0.26], "eye_coral", WHITE],
                               [[0.075, -0.125, 0.5], [0.135, -0.065, 0.56], "eye_coral", WHITE]], "eyes");
        this.arms = [this.limb(this.hull, [0.38, 0.05, 0.86], [
            [[-0.07, -0.07, -0.08], [0.07, 0.07, 0.08], "metal_dark", WHITE],
            [[-0.045, -0.045, -0.72], [0.045, 0.045, 0], "rust_body", WHITE],
            [[-0.15, -0.07, -0.8], [0.15, 0.07, -0.72], "magnet", WHITE],
            [[-0.15, -0.07, -0.95], [-0.07, 0.07, -0.8], "magnet", WHITE],
            [[0.07, -0.07, -0.95], [0.15, 0.07, -0.8], "magnet", WHITE],
            [[-0.15, -0.07, -1.0], [-0.07, 0.07, -0.95], "iron_block", WHITE],
            [[0.07, -0.07, -1.0], [0.15, 0.07, -0.95], "iron_block", WHITE]])];
    }

    buildBleep() {
        this.legs = [-0.28, 0.28].map(x => this.limb(this.body, [x, 0, 0.16], [[[-0.05, -0.16, -0.16], [0.05, 0.16, 0.16], "metal_dark", [0.9, 0.9, 0.95]]]));
        this.model(this.body, [[[-0.24, -0.24, 0.12], [0.24, 0.24, 0.52], "bleep_body", WHITE]]);
        this.head = this.node(this.body, [0, 0, 0.52], "head");
        this.model(this.head, [[[-0.2, -0.2, 0], [0.2, 0.2, 0.32], faces("bleep_face", "bleep_body"), WHITE],
                               [[-0.02, -0.02, 0.32], [0.02, 0.02, 0.5], "iron_block", WHITE],
                               [[-0.05, -0.05, 0.5], [0.05, 0.05, 0.58], "lumen", WHITE]]);
    }

    // a Craft Bot: Club Coders' own little robot, its yellow face, a dock-coloured body, the club's mark on its chest
    buildBot() {
        this.legs = [-0.34, 0.34].map(x => this.limb(this.body, [x, 0, 0.2], [[[-0.07, -0.2, -0.2], [0.07, 0.2, 0.2], "metal_dark", WHITE]]));
        this.model(this.body, [[[-0.3, -0.3, 0.14], [0.3, 0.3, 0.68], "dock_side", WHITE],
                               [[-0.14, 0.3, 0.27], [0.14, 0.312, 0.55], "logo_mark", WHITE]]);
        this.arms = [-0.37, 0.37].map(x => this.limb(this.body, [x, 0.0, 0.6], [[[-0.06, -0.06, -0.36], [0.06, 0.06, 0], "iron_block", WHITE]]));
        this.head = this.node(this.body, [0, 0, 0.68], "head");
        this.model(this.head, [[[-0.26, -0.26, 0], [0.26, 0.26, 0.4], faces("bot_face", "copper_block"), WHITE],
                               [[-0.03, -0.03, 0.4], [0.03, 0.03, 0.6], "iron_block", WHITE],
                               [[-0.06, -0.06, 0.6], [0.06, 0.06, 0.7], "lumen", WHITE]]);
    }

    // a name (or a Bot's words) over it, facing you: white on a card of the club's navy, the card only as wide as
    // the words (craft_models.make_tag: a TextNode 0.28 high, its card a margin round the words)
    makeTag(text) {
        if (this.tag) this.tag.dispose(false, true);  // (its card and picture too)
        const words = String(text), H = 64, font = "48px Inter, 'Segoe UI', Arial, sans-serif";
        const probe = document.createElement("canvas").getContext("2d");
        probe.font = font;
        const W = Math.max(H, Math.ceil(probe.measureText(words).width) + 24), k = 0.31 / H;
        const plane = BABYLON.MeshBuilder.CreatePlane("label", {width: W * k, height: H * k}, this.sc.scene);
        const tex = new BABYLON.DynamicTexture("labeltex", {width: W, height: H}, this.sc.scene, true);
        tex.hasAlpha = true;
        const ctx = tex.getContext();
        ctx.clearRect(0, 0, W, H);
        ctx.fillStyle = "rgba(9,12,23,0.6)";
        ctx.fillRect(0, 0, W, H);
        ctx.font = font;
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.textBaseline = "alphabetic";
        ctx.fillText(words, W / 2, 49);
        tex.update(true);
        const m = new BABYLON.StandardMaterial("labelmat", this.sc.scene);
        m.diffuseTexture = tex;
        m.emissiveColor = new BABYLON.Color3(1, 1, 1);
        m.disableLighting = true;
        m.backFaceCulling = false;
        m.useAlphaFromDiffuseTexture = true;
        plane.material = m;
        plane.billboardMode = BABYLON.Mesh.BILLBOARDMODE_ALL;
        plane.isPickable = false;
        plane.parent = this.root;
        // (the window's TAG_Z is the words' baseline: the card's middle is a little above it)
        plane.position = v3(0, 0, (TAG_Z[this.kind] ?? 2.0) + 0.1);
        plane.renderingGroupId = 1;
        // (white on the line looks too, as the window draws it: its name tag is never in the line colour)
        this.tag = plane;
        this.tagText = text;
    }

    say(text) {  // a speech bubble (a Craft Bot's "say"), or back to the name with null
        const words = text || this.name;
        if (words && words !== this.tagText) this.makeTag(words);
    }

    // placed and posed from a record (craft_sim's: x, y, z, vx, vy, vz, yaw, pitch, flags). (The window's setP(p) is
    // rotation.x = -p here, its setH(h) rotation.y = -h, its setR(r) rotation.z = -r: Babylon's axes)
    update(s, dt) {
        this.t += dt;
        const flags = s.flags || 0;
        this.root.position = v3(s.x, s.y, s.z);
        this.root.rotation.y = -(s.yaw - 90) * DEG;
        const speed = Math.hypot(s.vx || 0, s.vy || 0);
        this.phase += dt * speed * 3.2;
        const moving = Math.min(1, speed / 3), a = Math.sin(this.phase) * moving * 38;
        this.legs.forEach((leg, k) => { leg.rotation.x = -(k % 2 === 0 ? a : -a) * DEG; });
        if (flags & sim.F_SWING) this.swing = 0.3;
        this.swing = Math.max(0, this.swing - dt);
        const hit = this.swing > 0 ? Math.sin(this.swing / 0.3 * Math.PI) : 0;
        if (this.kind === "rust") {  // (the magnet arm reaches forward, and swings up and down to grab)
            for (const arm of this.arms) arm.rotation.x = -(40 + 60 * hit + a * 0.15) * DEG;
            this.hull.position.y = Math.abs(Math.sin(this.phase * 2)) * 0.03 * moving;
        } else {
            this.arms.forEach((arm, k) => {
                let p = k === 0 ? -a * 0.8 : a * 0.8;
                if (k === 1 && this.swing > 0) p = 70 * hit;
                arm.rotation.x = -p * DEG;
            });
        }
        if (this.head) this.head.rotation.x = this.kind === "player" ? -clamp(s.pitch || 0, -60, 60) * DEG : 0;
        if (this.kind === "fluff") {  // (it bobs as it floats along; brushed, it is a smaller puff till it grows back)
            const bob = Math.sin(this.t * 3.0) * 0.03 + Math.abs(Math.sin(this.phase)) * 0.06 * moving;
            const bare = !!(flags & sim.F_SLEEP);
            this.puff.scaling.setAll(bare ? 0.72 : 1.0);
            this.puff.position.y = (bare ? 0.5 : 0.6) + bob;
        } else if (this.kind === "glitch") {
            this.nextShape -= dt;
            if (this.nextShape <= 0) {
                this.nextShape = 0.06 + Math.random() * 0.16;
                this.reshape();
            }
            this.cluster.position.y = 0.55 + Math.sin(this.t * 2.3) * 0.05;
        }
        if (this.kind === "player" && flags & sim.F_SLEEP) {  // (lying in a Recharge Pod)
            this.root.rotation.z = -90 * DEG;
            this.root.position.y = s.z + 0.3;
        } else this.root.rotation.z = 0;
        if (this.kind === "player") this.body.position.y = flags & sim.F_CAREFUL ? -0.2 : 0;
        const h = this.sc.hereAt(s.x, s.y, s.z);
        this.here[0] = h[0];
        this.here[1] = h[1];
        this.here[2] = flags & sim.F_HURT ? 1 : 0;
    }

    dispose() {
        if (this.tag) this.tag.dispose(false, true);
        this.root.dispose();
    }
}

export class ItemModel {  // a thing dropped: its little cube or card, turning and bobbing
    constructor(sc, id) {
        this.sc = sc;
        this.item = id;
        this.meshes = [];
        this.lines = [];
        this.here = [1, 0, 0];
        this.root = new BABYLON.TransformNode("item", sc.scene);
        this.m = sc.part("item", itemGeo(sc.atlas.where, id, 0.3), this.root, this);
        this.m.ccHere = this.here;
        this.t = Math.random() * 3;
    }

    update(s, dt) {
        this.t += dt;
        this.root.position = v3(s.x, s.y, s.z + 0.15 + Math.sin(this.t * 2.5) * 0.06);
        this.m.rotation.y = -this.t * 70 * DEG;
        const h = this.sc.hereAt(s.x, s.y, s.z);
        this.here[0] = h[0];
        this.here[1] = h[1];
    }

    dispose() { this.root.dispose(); }
}

function between(a, b, f) {
    if (!a || !(f > 0)) return {...(a || b)};
    if (f >= 1) return {...b};
    const out = {...b};
    for (const k of ["x", "y", "z", "vx", "vy", "vz"]) out[k] = (a[k] || 0) + ((b[k] || 0) - (a[k] || 0)) * f;
    out.yaw = a.yaw + wrapDeg(b.yaw - a.yaw) * f;
    out.pitch = a.pitch + wrapDeg(b.pitch - a.pitch) * f;
    return out;
}

async function inflate(bytes) {  // (zlib, as numpy's world was packed: the browser's own DecompressionStream)
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate"));
    return new Uint8Array(await new Response(stream).arrayBuffer());
}

// ---------- the game ----------
export class CraftGame {
    static detect(m) { return !!(m.game_rules && "day_length" in m.game_rules && Array.isArray(m.mods)); }

    constructor(app) {
        this.app = app;
        this.id = "craftlab";
        this.title = "Craft Lab";
        this.word = "bot";
        this.mods = ["mods/blocks.py", "mods/blueprints.py", "mods/world.py", "mods/rules.py", "mods/bots/<username>.py"];
        this.scene = new CraftScene(app.canvas, app.tier, app.engine);
        this.controlKind = "craft";
        this.noCodeKey = true;      // (the code panel is the Bot tab's CODE, as the window's: no C key)
        this.hud = new CraftHud();
        this.hud.onSelect = i => this.select(i);
        this.world = null;
        this.me = null;
        this.inventory = null;
        this.screen = null;
        this.menu = null;           // the Esc menu (CraftMenu)
        this.blueprints = [];       // the server's blueprints (craft_items.blueprints(), the mods' after): a number is its index
        this.botStatus = null;      // what your Craft Bot is doing (the server's bot_status)
        this.timeSpeed = 1.0;       // (the state's speed: the night fast-forwarding while everyone is in a Pod)
        this.careful = false;       // Careful mode (Ctrl): you won't step off an edge
        this.ctrlDown = false; this.ctrlUsed = false;
        this.devOn = false;         // the dev panel (`)
        this.air = 12.0;            // (craft_game.AIR: the server keeps your air; the page counts it as the window does)
        this.lesson = null;
        this.gameRules = {};
        this.dayT = 0.3;
        this.paused = false;
        this.names = new Map();     // id -> {name, colour, wear, role, owner}
        this.bubbles = new Map();
        this.latest = new Map();
        this.entities = new Map();
        this.pendingBlocks = [];
        this.joining = null;
        this.loading = false;
        // what I control, predicted as the window predicts it (craft_client.on_snapshot, client_tick)
        this.predictor = null;
        this.predFirst = 0;
        this.smoother = new ErrorSmoother({removeUp: false});
        this.lead = new LeadController();
        this.nextSeq = 1;
        this.snapSeq = 0;
        this.accum = 0;
        this.sentAt = new Map();
        this.drawFrom = null;
        this.meState = null;
        // the window's keys and mouse
        this.yaw = 90; this.pitch = -5;
        const V = app.params.get("cam");
        this.view = ["eyes", "behind", "front", "free"].includes(V) ? V : "eyes";
        this.watch = null;
        this.free = null;         // the free camera's place (game coordinates)
        this.fly = false;
        this.digAt = null; this.digProgress = 0; this.digHit = 0;
        this.placeAt = 0; this.stepAt = 0;
        this.lookAt = 0;
        this.mouse = {left: false, right: false};
        this.captured = false;
        this.handItem = undefined;
        this.handT = 0;
        this.demo = app.params.get("demo") || null;
        this.lockless = app.params.get("lock") === "0";  // (the tests: the mouse's buttons work without the pointer locked)
        this.bind();
        loadCraftData().then(({data, img}) => {
            if (this.disposed) return;
            if (!sim.B.blocks.length || sim.B.nBuiltIn !== data.n_built_in || sim.B.items.size < data.items.length) sim.useTables(data);
            this.data = data;
            this.img = img;
            for (const b of this.modsPending || []) sim.addModBlock(b);
            this.remakeAtlas();
            if (this.joining && this.joining.done) this.assemble();
        }, e => app.toast(`Craft Lab's pictures didn't load: ${e.message}`, false, 8000));
        document.body.classList.add("craftscreen");
    }

    remakeAtlas() {
        if (!this.data) return;
        const atlas = this.atlas = paintAtlas(this.data, this.img);
        this.tables = new Tables(atlas.where, this.data.atlas.tiles);
        setAtlas(atlas.url, atlas.where, this.data.atlas.tiles);
        this.scene.setAtlas(atlas, this.tables);
    }

    // the keyboard's extra keys, the mouse and the wheel (craft_client.keys, capture, read_mouse)
    bind() {
        const cv = this.app.canvas;
        this.onMove = e => {
            if (!this.captured || this.screen) return;
            this.yaw = ((this.yaw - e.movementX * MOUSE_SPEED) % 360 + 360) % 360;
            this.pitch = clamp(this.pitch - e.movementY * MOUSE_SPEED, -89, 89);
        };
        this.onDown = e => {
            if (this.screen || this.menu || e.pointerType === "touch") return;
            if (!this.captured && !this.lockless) {
                if (this.controlsPlayer() || this.view === "free" || this.view === "follow") this.capture(true);
                return;
            }
            if (e.button === 0) {
                this.mouse.left = true;
                const t = this.mobInSight();
                if (t !== null && this.controlsPlayer()) { this.act({type: "attack", target: t}); this.digHit = 0; }
            } else if (e.button === 2) {
                this.mouse.right = true;
                const t = this.controlsPlayer() ? this.mobInSight() : null;
                if (t !== null && t >= 128) {  // (a creature: brush a Fluff, trade with a Bleep)
                    this.act({type: "use_mob", target: t});
                    this.placeAt = 0.6;
                    return;
                }
                this.placeAt = 0;  // (a click places at once; holding repeats)
            }
        };
        this.onUp = e => {
            if (e.button === 0) this.mouse.left = false;
            if (e.button === 2) this.mouse.right = false;
        };
        this.onWheel = e => {
            if (this.screen || this.menu || !this.app.state.connected) return;
            e.preventDefault();
            this.wheel(e.deltaY > 0 ? 1 : -1);
        };
        this.onLock = () => {
            const was = this.captured;
            this.captured = document.pointerLockElement === cv;
            if (!this.captured) this.mouse.left = this.mouse.right = false;
            // (the browser keeps Esc for letting the mouse go: let go while playing, the Esc menu opens, as the
            // window's Esc does)
            const panel = $("panel");
            if (was && !this.captured && this.wantLock && !this.screen && !this.menu && this.controlsPlayer() &&
                !(panel && panel.classList.contains("open"))) this.openMenu();
        };
        this.onMenu = e => e.preventDefault();
        // (craft_client.keys: Ctrl on its own switches Careful mode, on letting it go if no other key went with it;
        // Ctrl+X throws the stack; ` the dev panel. Keys passes no key with Ctrl held, so these are read here)
        this.onKeyRaw = e => {
            if (!this.app.state.connected || this.app.keys.typing()) return;
            if (e.key === "Control") {
                if (!e.repeat) { this.ctrlDown = true; this.ctrlUsed = false; }
                return;
            }
            if (this.ctrlDown || e.ctrlKey) this.ctrlUsed = true;
            if (e.ctrlKey && (e.key === "x" || e.key === "X")) { e.preventDefault(); this.drop(true); return; }
            if (e.code === "Backquote" && !e.ctrlKey && !e.altKey) { e.preventDefault(); this.devOn = !this.devOn; }
        };
        this.onKeyUpRaw = e => {
            if (e.key !== "Control") return;
            const alone = this.ctrlDown && !this.ctrlUsed;
            this.ctrlDown = false;
            if (!alone || this.fly || this.screen || this.menu || !this.controlsPlayer() || this.app.keys.typing()) return;
            this.setCareful(!this.careful);
        };
        this.onBlur = () => { this.ctrlDown = false; this.ctrlUsed = true; };
        document.addEventListener("mousemove", this.onMove);
        cv.addEventListener("pointerdown", this.onDown);
        window.addEventListener("pointerup", this.onUp);
        cv.addEventListener("wheel", this.onWheel, {passive: false});
        cv.addEventListener("contextmenu", this.onMenu);
        document.addEventListener("pointerlockchange", this.onLock);
        window.addEventListener("keydown", this.onKeyRaw);
        window.addEventListener("keyup", this.onKeyUpRaw);
        window.addEventListener("blur", this.onBlur);
    }

    capture(on) {
        const cv = this.app.canvas;
        this.wantLock = on;
        try {
            if (on && document.pointerLockElement !== cv && cv.requestPointerLock) {
                const p = cv.requestPointerLock();
                if (p && p.catch) p.catch(() => {});
            } else if (!on && document.pointerLockElement === cv) document.exitPointerLock();
        } catch (e) { /* (no pointer lock here: the touch controls or the tests look about) */ }
    }

    // ---------- the server's messages ----------
    welcome(m) {
        this.me = m.me ?? null;
        this.lesson = m.lesson || {};
        this.gameRules = m.game_rules || {};
        this.design = m.design || null;
        this.predictor = null;
        this.eventT = -1;
        if (Array.isArray(m.mods)) this.takeMods(m.mods);
        const kept = (m.prefs || {}).camera;
        if (kept && VIEWS.includes(kept.mode) && !this.app.params.get("cam")) this.view = kept.mode;
        if (this.me === null && this.view !== "follow") this.view = "free";
        if (m.role !== "learner") {
            this.app.toast("Teacher: T the time of day, M creatures, G everyone to you, K a Bot kit for everyone, N Sandbox or Challenge, F9 pause", false, 8000);
        }
        if (m.new_world) this.app.toast("A new world is coming…", false, 4000);
    }

    takeMods(blocks) {  // (craft_client.take_mods: the learners' own blocks into the list, drawn in the atlas)
        if (!this.data) { this.modsPending = [...(this.modsPending || []), ...blocks]; return; }
        let added = false;
        for (const b of blocks || []) if (b && sim.addModBlock(b)) added = true;
        if (added) {
            this.remakeAtlas();
            if (this.world) for (let cx = 0; cx < this.world.X / CHUNK; cx++) for (let cy = 0; cy < this.world.Y / CHUNK; cy++) this.world.dirty.add(cx + "," + cy);
        }
    }

    message(m) {
        const now = performance.now();
        if (this.joining && !this.joining.done && m.type !== "world") {
            if (m.type === "blocks") { this.pendingBlocks.push(...(m.list || [])); return true; }
        }
        switch (m.type) {
            case "world_head":
                this.joining = {head: m, parts: new Map(), done: false};
                return true;
            case "world":
                if (!this.joining) return true;
                this.joining.done = true;
                this.joining.end = m;
                this.dayT = Number(m.time ?? this.dayT);
                this.assemble();
                return true;
            case "inventory":
                this.inventory = m;
                if (m.open && (!this.screen || this.screen.kind !== m.open)) this.openScreen(m);
                else if (this.screen) this.screen.update(m);
                return true;
            case "blueprints":  // (the list as the server has it: the mods' after the built-in ones)
                this.blueprints = Array.isArray(m.list) ? m.list : [];
                if (this.screen) this.screen.blueprintsChanged();
                return true;
            case "bot_status":
                this.botStatus = m;
                return true;
            case "armed": case "ring": case "streak":
                this.effect(m.type, ...[...(m.at || [0, 0, 0]), ...(m.more || [])]);
                return true;
            case "blocks": {
                if (!this.world) { this.pendingBlocks.push(...(m.list || [])); return true; }
                const mine = this.digAt;
                this.world.applyChanges((m.list || []).map(c => c.map(Number)));
                this.digAt = mine;
                return true;
            }
            case "say":
                this.hud.say(m.text, now);
                this.hud.addLog(m.text);
                return true;
            case "news":
                this.hud.say(m.text, now, 5);
                this.hud.addLog(m.text);
                this.app.addEvent(m.text || "");
                return true;
            case "sound":
                this.playSound(m.name, m.at, m.v ?? 1);
                return true;
            case "burst": {
                const at = m.at || [0, 0, 0];
                this.scene.burst(at[0], at[1], at[2], m.tile || "particle", m.n);
                return true;
            }
            case "bubble":
                this.bubbles.set(m.id, [String(m.text || "").slice(0, 40), now + 4000]);
                return true;
            case "state":
                this.dayT = Number(m.t ?? this.dayT);
                this.timeSpeed = Number(m.speed ?? 1) || 1;  // (the night fast-forwarding: the sky visibly speeds up)
                this.paused = !!m.paused;
                this.gameRules = m.rules || this.gameRules;
                for (const [t, words] of m.events || []) {  // (the last four each second: only the new ones)
                    if (t > (this.eventT ?? -1)) { this.eventT = t; this.app.addEvent(words); }
                }
                return true;
            case "roster":
                for (const [pid, info] of Object.entries(m.players || {})) this.names.set(Number(pid), Object.assign({kind: "player"}, info));
                for (const [bid, info] of Object.entries(m.bots || {})) this.names.set(Number(bid), Object.assign({kind: "bot"}, info));
                return true;
            case "lesson":
                this.lesson = m.lesson || this.lesson;
                if (Array.isArray(m.blocks)) this.takeMods(m.blocks);
                return false;
            default:
                return false;
        }
    }

    binary(data, now) {
        const kind = frameKind(data);
        if (kind === KIND_WORLD) {
            if (!this.joining) return;
            const dv = new DataView(data);
            this.joining.parts.set(dv.getUint16(1, true), new Uint8Array(data, 3));
            return;
        }
        if (kind !== KIND_SNAPSHOT) return;
        const snap = unpackSnapshot(data, CRAFT_FIELDS);
        this.app.pushSnap(snap, now);
        this.onSnapshot(snap, now);
    }

    // the world from its parts (craft_client.assemble_world): inflated, its light worked out, drawn
    async assemble() {
        const J = this.joining;
        if (!J || !J.done || !this.data || this.loading) return;
        this.loading = true;
        try {
            const head = J.head, parts = [...J.parts.keys()].sort((a, b) => a - b).map(k => J.parts.get(k));
            const total = parts.reduce((n, p) => n + p.length, 0), all = new Uint8Array(total);
            let o = 0;
            for (const p of parts) { all.set(p, o); o += p.length; }
            const n = head.blocks_len;
            const [blocks, meta] = await Promise.all([inflate(all.subarray(0, n)), inflate(all.subarray(n))]);
            if (this.disposed || this.joining !== J) return;
            const w = new sim.World(head.size, head.seed, head.spawn);
            w.load(blocks, meta);
            this.world = w;
            this.joining = null;
            if (this.pendingBlocks.length) { w.applyChanges(this.pendingBlocks); this.pendingBlocks = []; }
            this.predictor = null;
            this.latest = new Map();
            this.scene.setWorld(w);
            if (!this.free) this.free = [w.spawn[0], w.spawn[1], w.spawn[2] + 12];
            const sp = w.spawn;
            this.scene.updateChunks(sp[0], sp[1], 1e9, false);
        } catch (e) {
            this.app.toast(`The world didn't arrive whole: ${e.message}`, false, 8000);
        } finally {
            this.loading = false;
        }
    }

    myId() { return this.me; }

    itemId(key) { return sim.B.itemId[key] ?? null; }  // (the tests: an item by its key)

    creative() { return !!(this.inventory && this.inventory.creative); }

    controlsPlayer() { return this.me !== null && this.world !== null && this.view !== "free" && this.view !== "follow"; }

    // ---------- the prediction (craft_client.on_snapshot, client_tick) ----------
    predicting() {
        const S = this.app.state;
        return this.me !== null && !!this.world && S.connected && this.app.params.get("predict") !== "0";
    }

    onSnapshot(snap, rx) {
        this.snapSeq = snap.seq;
        this.lead.feed(snap.flags >> 4);
        const ents = new Map(snap.entities.map(e => [e.id, e]));
        this.latest = ents;
        const me = this.me !== null ? ents.get(this.me) : null;
        if (!me || !this.predicting()) { if (!me) this.predictor = null; return; }
        const state = {...me};
        delete state.id;
        const newest = this.predictor ? this.predictor.log.newest() : null;
        if (newest !== null && newest !== undefined && seqDiff(snap.ack, newest) > 3) {
            // (the server has run past every input we sent: our numbering carries on from the server's)
            this.nextSeq = (snap.ack + 3 + Math.floor(this.app.state.pingMs / 1000 / sim.STEP)) & SEQ_MASK;
            this.predictor = null;
        }
        if (!this.predictor) {
            if (!this.facedYet) { this.facedYet = true; this.yaw = state.yaw || this.yaw; }
            this.predictor = new Predictor(sim.makeStep(this.world, () => this.creative()), state, 0.05, new InputLog(this.nextSeq));
            this.predFirst = this.nextSeq;
            this.drawFrom = state;
            this.smoother.clear();
            this.accum = 0;
            return;
        }
        if (snap.ack === 0 || seqDiff(snap.ack, this.predFirst) < 0) return;
        for (const k of ["hp", "energy", "shield", "held"]) this.predictor.state[k] = state[k];  // (the server's own: never predicted)
        const err = this.predictor.correct(state, snap.ack, sim.STEP, sim.compare);
        const moved = this.predictor.movedFrom;
        if (moved) {
            const n = this.predictor.state, f = this.drawFrom;
            this.drawFrom = err === Infinity || !f ? n : {...f, x: f.x + n.x - moved.x, y: f.y + n.y - moved.y, z: f.z + n.z - moved.z};
            if (err !== Infinity) this.smoother.add([moved.x - n.x, moved.y - n.y, moved.z - n.z], 0);
        }
        const sent = this.sentAt.get(snap.ack);
        if (sent !== undefined && rx && this.app.ctrl) {
            const ms = rx - sent;
            this.app.ctrl.ctrlMs = this.app.ctrl.ctrlMs === null ? ms : this.app.ctrl.ctrlMs * 0.8 + ms * 0.2;
        }
    }

    sendNeutral() {
        const seq = this.nextSeq;
        this.nextSeq = (seq + 1) & SEQ_MASK;
        this.app.sendBinary(packInput(seq, this.snapSeq, Math.floor(performance.now()) >>> 0, 0, 0, this.fly && this.creative() ? sim.FLY_B : 0, []));
    }

    // this tick's input (craft_client.read_keys): where to go in the world's frame, by the keys and the way you look,
    // and the buttons (jump, sprint, careful, fly). play.js calls it with the keys, a pad (or the touch controls).
    // Shift held runs; Careful mode (Ctrl) is kept on until Ctrl is pressed again; flying (F, Sandbox), Space goes up
    // and Ctrl down. A pad: the stick walks (pushed all the way: runs), A (south) jumps, B (east) Careful mode, X
    // (west) the Backpack, Y (north) its Bot tab, the bumpers along the Toolbelt, the right stick looks about, the
    // triggers dig and place (digAndPlace). The touch controls: RUN held, CROUCH (Careful), BAG, FLY, DROP
    keysInput(K, pad, tapped) {
        const flyB = this.fly && this.creative() ? sim.FLY_B : 0;
        if (this.screen && pad && (pad.pressed.has("west") || pad.pressed.has("north"))) { pad.pressed = new Set(); this.toggleInventory(); }  // (X or Y again, BAG: it shuts)
        if (this.screen || this.menu || !this.controlsPlayer() || K.typing()) return {throttle: 0, steer: 0, buttons: flyB};
        if (this.demo === "walk") {  // (the tests: walk in a slow circle, jumping now and then: craft_client.demo_input)
            const t = performance.now() / 1000, yr = (90 + t * 12) * DEG;
            return {throttle: Math.cos(yr) * 0.6, steer: Math.sin(yr) * 0.6, buttons: Math.floor(t * 2) % 5 === 0 ? sim.JUMP_B : 0};
        }
        let f = (K.is("w", "ArrowUp") ? 1 : 0) - (K.is("s", "ArrowDown") ? 1 : 0);
        let r = (K.is("d", "ArrowRight") ? 1 : 0) - (K.is("a", "ArrowLeft") ? 1 : 0);
        let bt = 0;
        if (K.is(" ")) bt |= sim.JUMP_B;
        if (K.is("Shift")) bt |= sim.SPRINT_B;
        if (pad) {
            if (!f && !r) {
                f = pad.y || 0; r = pad.x || 0;
                if (Math.hypot(pad.x || 0, pad.y || 0) > 0.95 && pad.name !== "touch") bt |= sim.SPRINT_B;  // (the stick pushed all the way: run)
            }
            if (pad.held.has("south")) bt |= sim.JUMP_B;
            if (pad.held.has("run")) bt |= sim.SPRINT_B;
            if (pad.rx) this.yaw = ((this.yaw - pad.rx * 3.0) % 360 + 360) % 360;
            if (pad.ry) this.pitch = clamp(this.pitch + pad.ry * 2.0, -89, 89);
            if (pad.pressed.has("east")) this.setCareful(!this.careful);
            if (pad.pressed.has("lb")) this.wheel(-1);
            if (pad.pressed.has("rb")) this.wheel(1);
            if (pad.pressed.has("fly")) this.toggleFly();
            if (pad.pressed.has("drop")) this.drop(false);
            const open = pad.pressed.has("west") ? "backpack" : pad.pressed.has("north") ? "bot" : null;
            pad.pressed = new Set();
            if (open) { this.toggleInventory(open); return {throttle: 0, steer: 0, buttons: flyB}; }
        }
        if (this.fly && this.creative()) {
            bt |= sim.FLY_B;
            if (this.ctrlDown) bt |= sim.CAREFUL_B;  // (flying: Ctrl goes down)
        } else {
            this.fly = false;
            if (this.careful) bt |= sim.CAREFUL_B;
        }
        const yr = this.yaw * DEG, fx = Math.cos(yr), fy = Math.sin(yr), rx = Math.sin(yr), ry = -Math.cos(yr);
        let mx = f * fx + r * rx, my = f * fy + r * ry;
        const n = Math.hypot(mx, my);
        if (n > 1) { mx /= n; my /= n; }
        return {throttle: mx, steer: my, buttons: bt};
    }

    // play.js every frame: whole 1/60 s ticks, each one input (predicted, numbered and sent)
    controlFrame(now, readKeys, dt) {
        if (!this.predictor || this.paused) return;
        this.accum = Math.min(15 * sim.STEP, this.accum + dt / this.lead.multiplier());
        while (this.accum >= sim.STEP) {
            this.accum -= sim.STEP;
            const k = readKeys();
            const inp = quantiseInput(k.throttle, k.steer, k.buttons);
            this.drawFrom = this.predictor.state;
            const seq = this.predictor.apply(inp, sim.STEP, now);
            const prev = this.predictor.log.previous(2);
            this.nextSeq = this.predictor.log.nextSeq;
            this.sentAt.set(seq, now);
            if (this.sentAt.size > 128) for (const s of [...this.sentAt.keys()].slice(0, 64)) this.sentAt.delete(s);
            this.app.sendBinary(packInput(seq, this.snapSeq, Math.floor(now) >>> 0, inp[0], inp[1], inp[2], prev));
        }
    }

    // ---------- acting (craft_client.act, predict_action) ----------
    act(msg) {
        this.app.send(msg);
        const kind = msg.type;
        if (kind === "dig" && this.world) {  // (shown at once: the server's answer puts it right if it says no)
            const {x, y, z} = msg, b = sim.B.blocks[this.world.get(x, y, z)];
            this.world.set(x, y, z, 0, 0);
            this.scene.burst(x, y, z, b && b.tiles ? b.tiles[1] : "particle");
            this.playSound("dig_" + String((b && b.tool) || "soft"), [x + 0.5, y + 0.5, z + 0.5]);
        } else if (kind === "select" && this.inventory) this.inventory.selected = msg.slot;
    }

    select(i) {
        if (this.screen || !this.controlsPlayer()) return;
        this.act({type: "select", slot: i % TOOLBELT});
    }

    // the wheel (and a pad's bumpers): along the Toolbelt
    wheel(step) {
        if (this.inventory && this.controlsPlayer() && !this.screen) this.select(((this.inventory.selected || 0) + step + TOOLBELT) % TOOLBELT);
    }

    drop(all) {
        if (!this.screen && !this.menu && this.controlsPlayer()) this.act({type: "drop", all});
    }

    // F: Sandbox players fly (Space up, Ctrl down) or walk
    toggleFly() {
        if (!this.creative()) return;
        this.fly = !this.fly;
        this.hud.say(this.fly ? "Flying: Space up, Ctrl down" : "Walking", performance.now(), 1.5);
    }

    // Ctrl (a pad's B, the touch controls' CROUCH): Careful mode, the CAREFUL tag on the HUD
    setCareful(on) { this.careful = !!on; }

    // I: the Backpack (on its Backpack tab); B: on its Bot tab. Again: it shuts (craft_client.toggle_inventory)
    toggleInventory(tab = "backpack") {
        if (this.screen) { this.act({type: "close"}); this.closeScreen(); return; }
        if (this.menu || !this.controlsPlayer() || !this.inventory) return;
        this.act({type: "tab", tab});
        this.openScreen({...this.inventory, open: null, tab});
    }

    openScreen(msg) {
        if (this.screen) this.screen.destroy();
        this.closeMenu(false);
        this.screen = new CraftScreen(msg, m => this.act(m), {
            shiftHeld: () => this.app.keys.down.has("Shift"), blueprints: () => this.blueprints,
            nearFab: () => this.nearFabricator(), botHub: kind => this.botHub(kind), close: () => this.toggleInventory()});
        this.capture(false);
        this.mouse.left = this.mouse.right = false;
    }

    closeScreen(relock = true) {
        if (this.screen) { this.screen.destroy(); this.screen = null; }
        if (relock) this.capture(true);
    }

    // is a Fabricator within 4 blocks (the Blueprints tab says which need one: the server checks again)?
    // (craft_client.near_fabricator)
    nearFabricator() {
        const s = this.meState, w = this.world, fab = sim.B.id.fabricator;
        if (!s || !w || fab === undefined) return false;
        const cx = s.x, cy = s.y, cz = s.z + 1, x0 = Math.floor(cx), y0 = Math.floor(cy), z0 = Math.floor(cz);
        for (let dx = -4; dx <= 4; dx++) for (let dy = -4; dy <= 4; dy++) for (let dz = -4; dz <= 4; dz++) {
            if (w.get(x0 + dx, y0 + dy, z0 + dz) !== fab) continue;
            if (Math.hypot(x0 + dx + 0.5 - cx, y0 + dy + 0.5 - cy, z0 + dz + 0.5 - cz) <= FAB_REACH + 0.9) return true;
        }
        return false;
    }

    // the Bot tab's GARAGE, CODE and BRAIN: the Backpack shuts and the page's own panel opens (the Garage tab of the
    // side panel, the code panel, the brain editor), as the window's bot_hub
    botHub(kind) {
        if (this.screen) { this.act({type: "close"}); this.closeScreen(false); }
        const app = this.app;
        if (kind === "garage") {
            const panel = $("panel");
            if (panel) panel.classList.add("open");
            const b = document.querySelector('#panelhead button[data-tab="garage"]');
            if (b) b.click();
            else { app.state.tab = "garage"; app.renderPanel(); }
        } else if (kind === "code") {
            if (app.openCode) app.openCode();
        } else if (app.openBrainEditor) app.openBrainEditor();
    }

    // ---------- the Esc menu (craft_ui.Menu): the logo, RESUME, GRAPHICS, CREDITS, QUIT ----------
    openMenu() {
        if (this.menu) return;
        this.menu = new CraftMenu({
            tier: this.app.tier, tiers: TIERS, resume: () => this.closeMenu(true), chooseTier: t => this.app.setTier(t),
            quitWords: this.app.state.role === "learner" ? "QUIT: BACK TO THE LOBBY" : "QUIT: BACK TO THE DESK",
            quit: () => {  // (as the page leaves now: the lobby, pressed twice, or the desk)
                const b = [$("btn-lobby"), $("btn-desk")].find(x => x && !x.hidden);
                if (!b) return null;
                b.click();
                if (!this.menu) return null;
                return /SURE/.test(b.textContent) ? b.textContent : null;
            }});
        this.menu.el.addEventListener("pointerdown", e => { if (e.target === this.menu.el) this.closeMenu(false); });  // (a click beside the card: the mouse kept free)
        this.mouse.left = this.mouse.right = false;
        this.capture(false);
    }

    closeMenu(relock = true) {
        if (!this.menu) return;
        this.menu.destroy();
        this.menu = null;
        if (relock) this.capture(true);
    }

    // an Overload Cell armed (it pulses magenta), its pulse (a ring of cyan sparks), a Glitch pulled home (craft_client.effect):
    // the scene's own when it has them, else a burst of sparks for the pulse
    effect(kind, ...at) {
        const sc = this.scene;
        if (sc.effects && typeof sc.effects[kind] === "function") { sc.effects[kind](...at); return; }
        if (kind === "ring") sc.burst(at[0] - 0.5, at[1] - 0.5, at[2] - 0.5, "spark", 40);
    }

    lookTarget() {
        const s = this.meState;
        if (!s || !this.world) return null;
        const [ex, ey, ez] = sim.eye(s), [dx, dy, dz] = sim.lookDir(this.yaw, this.pitch);
        return sim.ray(this.world, ex, ey, ez, dx, dy, dz, this.creative() ? sim.REACH_CREATIVE : sim.REACH);
    }

    // the creature (or player) in the middle of the screen, within reach, nearer than any block
    mobInSight() {
        const s = this.meState;
        if (!s) return null;
        const [ex, ey, ez] = sim.eye(s), [dx, dy, dz] = sim.lookDir(this.yaw, this.pitch);
        const hit = this.lookTarget();
        let best = null, bd = hit ? Math.min(3.6, hit[2]) : 3.6;
        for (const [eid, e] of this.entities) {
            if (eid === this.me || e.kind === 6) continue;
            const cx = e.x - ex, cy = e.y - ey, cz = e.z + 0.8 - ez;
            const along = cx * dx + cy * dy + cz * dz;
            if (along <= 0 || along > bd) continue;
            const off = Math.sqrt(Math.max(0, cx * cx + cy * cy + cz * cz - along * along));
            if (off < 0.7) { best = eid; bd = along; }
        }
        return best;
    }

    // the left button held digs what you look at (its time from the block and what you hold); the right button puts
    // what you hold beside it, or uses it (craft_client.dig_and_place)
    digAndPlace(dt) {
        const sc = this.scene;
        if (this.screen || this.menu || !this.controlsPlayer() || !this.world) { this.digAt = null; this.digProgress = 0; sc.showTarget(null, 0); return; }
        const hit = this.lookTarget();
        const ctrl = this.app.ctrl, pad = ctrl && ctrl.pad;
        const touchOn = this.app.touch && this.app.touch.shown;
        let left = this.captured || touchOn || this.lockless ? this.mouse.left : false;
        let right = this.captured || touchOn || this.lockless ? this.mouse.right : false;
        if (pad) { left = left || pad.rt > 0.5; right = right || pad.lt > 0.5; }
        this.digHit = Math.max(0, this.digHit - dt);
        if (!hit) {
            this.digAt = null;
            sc.showTarget(null, 0);
        } else {
            const [pos, face] = hit, key = pos.join(",");
            if (left && this.mobInSight() === null) {
                if (this.digAt !== key) {
                    this.digAt = key;
                    this.digProgress = 0;
                    this.act({type: "dig_start", x: pos[0], y: pos[1], z: pos[2]});
                }
                const held = this.inventory ? this.inventory.inv[this.inventory.selected] : null;
                const [t] = sim.digTime(this.world.get(...pos), held ? sim.itemOf(held[0]) : null);
                if (t === null) this.digProgress = 0;
                else {
                    this.digProgress += dt / (this.creative() ? 0.12 : t);
                    if (this.digProgress >= 1.0) {
                        this.act({type: "dig", x: pos[0], y: pos[1], z: pos[2]});
                        this.digAt = null;
                        this.digProgress = 0;
                        this.digHit = this.creative() ? 0.15 : 0;
                    } else if (this.stepAt <= 0) {
                        const b = sim.B.blocks[this.world.get(...pos)];
                        this.playSound("dig_" + String((b && b.tool) || "soft"), [pos[0] + 0.5, pos[1] + 0.5, pos[2] + 0.5], 0.4);
                        sc.burst(pos[0], pos[1], pos[2], b && b.tiles ? b.tiles[1] : "particle", 3, 1.5);
                        this.stepAt = 0.25;
                    }
                }
            } else {
                this.digAt = null;
                this.digProgress = 0;
            }
            sc.showTarget(pos, this.digProgress);
            if (right) {
                this.placeAt -= dt;
                if (this.placeAt <= 0) {
                    this.placeAt = PLACE_GAP;
                    this.act({type: "right", x: pos[0], y: pos[1], z: pos[2], face: [...face]});
                }
            }
        }
        if (!hit && right) {
            this.placeAt -= dt;
            if (this.placeAt <= 0) { this.placeAt = PLACE_GAP * 2; this.act({type: "use_item"}); }
        }
        if (!right) this.placeAt = 0;
    }

    // ---------- each frame ----------
    frame(now, dt) {
        const sc = this.scene;
        this.stepAt -= dt;
        // what to draw: the others blended between snapshots, my own player where the prediction has it
        const pair = this.app.samplePair(now), drawn = new Map();
        if (pair) {
            const {a, b, f} = pair, byId = b ? new Map(b.entities.map(e => [e.id, e])) : new Map();
            for (const e of a.entities) drawn.set(e.id, byId.has(e.id) ? between(e, byId.get(e.id), f) : e);
        }
        if (this.predictor) {
            const mine = {...this.predictor.state}, f = this.accum / sim.STEP;
            if (this.drawFrom) for (const k of ["x", "y", "z"]) mine[k] = this.drawFrom[k] + (mine[k] - this.drawFrom[k]) * f;
            const [[ox, oy, oz]] = this.smoother.offset(dt);
            mine.x += ox; mine.y += oy; mine.z += oz;
            mine.id = this.me;
            drawn.set(this.me, mine);
            this.meState = mine;
        } else if (this.me !== null && drawn.has(this.me)) this.meState = drawn.get(this.me);
        else if (this.me === null) this.meState = null;
        this.entities = drawn;
        const length = (this.gameRules || {}).day_length || 900;
        if ((this.gameRules || {}).time_runs !== false && !this.paused) this.dayT = (this.dayT + dt * (this.timeSpeed || 1) / length) % 1.0;
        if (now - this.lookAt > 100 && this.controlsPlayer()) {
            this.lookAt = now;
            this.app.send({type: "look", yaw: Math.round(this.yaw * 10) / 10, pitch: Math.round(this.pitch * 10) / 10});
        }
        if (!this.world || !sc.mats) {
            sc.setTime(this.dayT);
            this.hud.update({now, hidden: true, title: this.titleText(), dev: this.world ? "" : "Craft Lab: the world is on its way…"});
            return;
        }
        if (this.app.touch && this.app.touch.shown && this.app.touch.takeLook) {  // (a phone: a finger dragged looks about)
            const [lx, ly] = this.app.touch.takeLook();
            this.yaw = ((this.yaw - lx * 0.3) % 360 + 360) % 360;
            this.pitch = clamp(this.pitch - ly * 0.3, -89, 89);
        }
        this.digAndPlace(dt);
        const cam = this.placeCamera(dt);
        sc.setTime(this.dayT);
        sc.tick(dt, cam);
        sc.updateChunks(cam[0], cam[1], 8);
        this.syncModels(dt, cam);
        sc.updateBits(dt);
        this.handUpdate(dt);
        this.overlay(now);
        if (this.app.touch && this.app.touch.shown) this.app.touch.setLayout("craft");
        if (this.app.sound && this.app.sound.craftFrame) this.app.sound.craftFrame(this.dayT, this.meState);
        const shown = `${this.view}:${this.watch}:${this.me}`;
        if (shown !== this.shownKeys) {
            this.shownKeys = shown;
            if (this.app.keyHelp) this.app.keyHelp();
            this.app.updatePills();
        }
    }

    // the camera (craft_client.place_camera): your eyes, behind you or in front; the teacher's free camera and
    // following a learner. Returns the camera's place (game coordinates)
    placeCamera(dt) {
        const cam = this.scene.camera, w = this.world;
        let s = this.meState, mode = this.view;
        if (mode === "follow") {
            s = this.watch !== null ? this.entities.get(this.watch) : null;
            if (!s) mode = this.me !== null ? "eyes" : "free";
        } else if (mode !== "free" && !s) mode = "free";
        if (mode === "free") {
            if (!this.free) this.free = [w.spawn[0], w.spawn[1], w.spawn[2] + 12];
            const K = this.app.keys, typing = K.typing() || this.screen || this.menu;
            const f = typing ? 0 : (K.is("w", "ArrowUp") ? 1 : 0) - (K.is("s", "ArrowDown") ? 1 : 0);
            const r = typing ? 0 : (K.is("d", "ArrowRight") ? 1 : 0) - (K.is("a", "ArrowLeft") ? 1 : 0);
            const u = typing ? 0 : (K.is(" ") ? 1 : 0) - (this.ctrlDown ? 1 : 0);  // (Space up, Ctrl down, as flying)
            const [dx, dy, dz] = sim.lookDir(this.yaw, this.pitch), yr = this.yaw * DEG, sp = (K.is("Shift") ? 30 : 18) * dt;
            this.free[0] = clamp(this.free[0] + (dx * f + Math.sin(yr) * r) * sp, -40, w.X + 40);
            this.free[1] = clamp(this.free[1] + (dy * f - Math.cos(yr) * r) * sp, -40, w.Y + 40);
            this.free[2] = clamp(this.free[2] + (dz * f + u) * sp, 1, w.Z + 60);
            const [x, y, z] = this.free;
            cam.position = v3(x, y, z);
            cam.setTarget(v3(x + dx, y + dy, z + dz));
            return [x, y, z];
        }
        let [ex, ey, ez] = sim.eye(s);
        if ((s.flags || 0) & sim.F_SLEEP) ez = s.z + 0.4;
        // (following a learner: from behind them, turning as they turn; the mouse tilts the view up and down)
        let vyaw = this.yaw;
        if (mode === "follow") {
            this.followYaw = this.followYaw === undefined ? s.yaw : this.followYaw + wrapDeg(s.yaw - this.followYaw) * Math.min(1, dt * 3);
            vyaw = this.followYaw;
        } else this.followYaw = undefined;
        const [dx, dy, dz] = sim.lookDir(vyaw, mode === "follow" ? clamp(this.pitch, -60, 20) : this.pitch);
        if (mode === "eyes") {
            cam.position = v3(ex, ey, ez);
            cam.setTarget(v3(ex + dx, ey + dy, ez + dz));
            return [ex, ey, ez];
        }
        const back = mode === "front" ? 1 : -1;
        let dist = 4.5;
        const rx = Math.sin(vyaw * DEG) * 0.6, ry = -Math.cos(vyaw * DEG) * 0.6;
        let ox = dx * back + (back < 0 ? rx : 0), oy = dy * back + (back < 0 ? ry : 0), oz = dz * back + 0.35;
        const n = Math.hypot(ox, oy, oz);
        ox /= n; oy /= n; oz /= n;
        const hit = sim.ray(w, ex, ey, ez, ox, oy, oz, dist);
        if (hit) dist = Math.max(0.6, hit[2] - 0.3);
        const px = ex + ox * dist, py = ey + oy * dist, pz = ez + oz * dist;
        cam.position = v3(px, py, pz);
        if (mode === "front") cam.setTarget(v3(ex, ey, ez));
        else cam.setTarget(v3(ex + dx * 6, ey + dy * 6, ez + dz * 6));
        return [px, py, pz];
    }

    // a model for each player, creature, Bot and thing dropped near enough to see (not your own, in your eyes)
    syncModels(dt, cam) {
        const sc = this.scene, models = sc.models, reach = sc.view() * 0.8;
        for (const [eid, m] of [...models]) if (!this.entities.has(eid)) { m.dispose(); models.delete(eid); }
        for (const [eid, e] of this.entities) {
            if (eid === this.me && this.view === "eyes" && this.controlsPlayer()) {
                if (models.has(eid)) { models.get(eid).dispose(); models.delete(eid); }
                continue;
            }
            const far = (e.x - cam[0]) ** 2 + (e.y - cam[1]) ** 2 > reach * reach;
            let m = models.get(eid);
            if (far) { if (m) { m.dispose(); models.delete(eid); } continue; }
            const kind = e.kind || 0;
            if (m && m.item !== undefined && kind === 6 && m.item !== e.held) { m.dispose(); models.delete(eid); m = null; }
            if (!m) {
                if (kind === 6) m = new ItemModel(sc, e.held);
                else {
                    const kname = sim.KIND_NAMES[kind] || "player", info = this.names.get(eid) || {};
                    m = new Model(sc, kname, info.colour || [60, 130, 230], (kname === "player" || kname === "bot") && eid !== this.me ? info.name || null : null);
                }
                models.set(eid, m);
            }
            m.update(e, dt);
            if (kind === 0 && m.wear) m.wear((this.names.get(eid) || {}).wear);
            const said = this.bubbles.get(eid);
            if (said && m.say) m.say(performance.now() < said[1] ? said[0] : null);
        }
    }

    // what you hold, at the bottom right in your eyes' view (craft_client.hand_setup, hand_update)
    handUpdate(dt) {
        const sc = this.scene, s = this.meState;
        const show = this.view === "eyes" && this.controlsPlayer() && !!s && !!sc.atlas;
        const held = this.inventory ? this.inventory.inv[this.inventory.selected] : null, item = held ? held[0] : null;
        if (!sc.hand || sc.hand.isDisposed() || this.handItem !== item || this.handScene !== sc.scene) {
            if (sc.hand && !sc.hand.isDisposed()) sc.hand.dispose();
            this.handScene = sc.scene;
            this.handItem = item;
            const node = sc.hand = new BABYLON.TransformNode("hand", sc.scene);
            node.parent = sc.camera;
            const holder = {meshes: [], lines: []};
            const g = item === null ? boxGeo(sc.atlas.where, [[[-0.07, -0.07, -0.25], [0.07, 0.07, 0.1], "skin", [1, 1, 1]]])
                : itemGeo(sc.atlas.where, item, (sim.B.items.get(item) || {}).block === null || (sim.B.items.get(item) || {}).block === undefined ? 0.22 : 0.13);
            const m = sc.part("hand", g, node, holder);
            this.handHere = [1, 0, 0];
            m.ccHere = this.handHere;
            if (item !== null) m.rotation = new BABYLON.Vector3(0, -30 * DEG, 10 * DEG);
            for (const x of [m, ...holder.lines]) x.renderingGroupId = 2;
            sc.handMeshes = [m, ...holder.lines];
        }
        sc.hand.setEnabled(show);
        // (a light carried: a held Glowfruit's, round your eyes: craft_gfx.set_held_light)
        const it = item !== null ? sim.B.items.get(item) : null;
        sc.setHeldLight(s && this.controlsPlayer() && it ? it.glow || 0 : 0, s ? sim.eye(s) : null);
        if (!show) return;
        this.handT += dt * Math.hypot(s.vx || 0, s.vy || 0);
        const bob = Math.sin(this.handT * 2.2) * 0.02;
        const swing = this.digAt !== null || this.digHit > 0 ? Math.sin(performance.now() / 1000 * 14) * 25 : 0;
        // (the window draws the hand with a camera of its own, 70 degrees across: here, in the 75-degree camera, it is
        // made bigger and further out by as much, so it looks the same size in the same place)
        const k = Math.tan(37.5 * DEG) / Math.tan(35 * DEG);
        sc.hand.position = new BABYLON.Vector3(0.38 * k, (-0.26 + bob) * k, 0.78 * k);
        sc.hand.scaling = new BABYLON.Vector3(k, k, k);
        sc.hand.rotation.x = Math.abs(swing) * DEG;
        const h = sc.hereAt(s.x, s.y, s.z + 1);
        this.handHere[0] = h[0];
        this.handHere[1] = h[1];
    }

    // the HUD (craft_client.overlay): the Toolbelt, Health, Energy and Shield, the crosshair's ring (digging, or your
    // air under water), Careful mode, the Bot's line, the dev panel
    overlay(now) {
        const s = this.meState, w = this.world;
        let under = false, ex = 0, ey = 0, ez = 0;
        if (s && w) {
            [ex, ey, ez] = sim.eye(s);
            under = w.get(Math.floor(ex), Math.floor(ey), Math.floor(ez)) === sim.B.id.water;
        }
        const dt = Math.min(0.1, (now - (this.airAt ?? now)) / 1000);  // (the server keeps your air: counted the same way to show it)
        this.airAt = now;
        this.air = under ? Math.max(0, this.air - dt) : Math.min(AIR, this.air + dt * 4);
        if (this.devOn && now - (this.devAt || 0) > 250) { this.devAt = now; this.devText = this.devWords(s, ex, ey, ez); }
        this.hud.update({inv: this.inventory, hp: s ? s.hp ?? 100 : 100, energy: s ? s.energy ?? 100 : 100, shield: s ? s.shield || 0 : 0,
                         shieldMax: (this.inventory || {}).shield_max || 0, creative: this.creative(),
                         dig: this.digAt !== null ? this.digProgress : 0, air: this.air, airMax: AIR, underWater: under,
                         careful: this.careful && !this.fly && this.controlsPlayer(), bot: this.botWords(),
                         hurt: !!(s && (s.flags & sim.F_HURT)), now, hidden: !this.controlsPlayer(),
                         title: this.titleText(), dev: this.devOn ? this.devText || "" : ""});
    }

    // the dev panel (`): POSITION, CHUNK, LIGHT, FPS, TIER, SERVER, TIME, as the window's
    devWords(s, ex, ey, ez) {
        const t = this.dayT, w = this.world, sc = this.scene;
        const phase = t < DUSK ? "day" : t < NIGHT ? "dusk" : t < DAWN ? "night" : "dawn";
        const pos = s ? `x ${s.x.toFixed(1)}  y ${s.y.toFixed(1)}  z ${s.z.toFixed(1)}` : this.free ? `x ${this.free[0].toFixed(1)}  y ${this.free[1].toFixed(1)}  z ${this.free[2].toFixed(1)}` : "";
        const at = s || (this.free ? {x: this.free[0], y: this.free[1]} : {x: 0, y: 0});
        const xi = Math.floor(ex), yi = Math.floor(ey), zi = Math.floor(ez);
        const light = s && w && w.inside(xi, yi, zi) ? [w.sky[w.at(xi, yi, zi)], w.glow[w.at(xi, yi, zi)]] : [0, 0];
        const fps = this.app.engine && this.app.engine.getFps ? this.app.engine.getFps() : 0;
        const S = this.app.state;
        return `POSITION  ${pos}\n          looking ${this.yaw.toFixed(0)} ${this.pitch.toFixed(0)}\n` +
            `CHUNK     ${Math.floor(at.x / CHUNK)}, ${Math.floor(at.y / CHUNK)}   (${sc.chunks ? sc.chunks.size : 0} drawn, ${sc.todo ? sc.todo.size : 0} to draw)\n` +
            `LIGHT     sky ${light[0]}  block ${light[1]}  (of ${sim.B.lightMax})\n` +
            `FPS       ${Math.round(fps)}\nTIER      ${sc.tier}\n` +
            `SERVER    ping ${Math.round(S.pingMs || 0)} ms   things ${this.entities.size}\nTIME      ${t.toFixed(3)} (${phase})`;
    }

    // the status card's Bot line: what your Craft Bot is doing ("Bot: digging, 12 dug, 3 placed")
    botWords() {
        const m = this.botStatus;
        if (!m) return "";
        const words = {dig: "digging", place: "building", forward: "moving", back: "moving", up: "moving", down: "moving",
                       left: "turning", right: "turning", bump: "bumped", wait: "thinking"};
        const doing = m.doing || "waiting", st = m.stats || {};
        const what = m.running ? words[doing] || doing : "parked";
        return `Bot: ${what}, ${st.dug || 0} dug, ${st.placed || 0} placed`;
    }

    titleText() {
        const S = this.app.state, V = this.view;
        const watching = V === "follow" && this.watch !== null ? ` · watching ${this.nameOf(this.watch)}` : V === "free" ? " · flying free" : "";
        return `CRAFT LAB   ${S.role === "learner" ? "online" : "TEACHER"}: ${S.name || ""}${watching}${this.paused ? " · PAUSED" : ""}`;
    }

    nameOf(id) {
        const n = this.names.get(id);
        return n ? n.name : `#${id}`;
    }

    // a sound the game names (craft_sound.Sounds.play): quieter the further it is from you, none past 32 m
    playSound(name, at, volume = 1) {
        const snd = this.app.sound;
        if (!snd || !snd.craftPlay) return;
        const s = this.meState, listener = s ? sim.eye(s) : this.free;
        snd.craftPlay(name, at, listener, volume);
    }

    // ---------- the keys app.js passes on ----------
    // (craft_client.keys: 1-8 the Toolbelt, I the Backpack, B its Bot tab, X throw one (Ctrl+X the stack: onKeyRaw),
    // V the view, ` the dev panel (onKeyRaw), H the keys, F flying in Sandbox, Shift held runs, Ctrl alone Careful
    // mode (onKeyRaw), Tab the lessons, U, P; the teacher's T, M, G, K, N, F9; Esc the menu)
    onKey(k, e) {
        const S = this.app.state, teacher = S.role !== "learner";
        if (k === "Escape") {
            if (this.menu) { this.closeMenu(true); return true; }
            if (this.screen) { this.act({type: "close"}); this.closeScreen(true); return true; }
            if (this.controlsPlayer()) { this.openMenu(); return true; }
            return false;
        }
        if (this.menu) return k !== "Tab";
        if ((k === "i" || k === "b") && (this.screen || this.controlsPlayer())) { this.toggleInventory(k === "b" ? "bot" : "backpack"); return true; }
        if (k === "c") return true;  // (the code panel is the Bot tab's CODE, as the window's)
        if (this.screen) return /^[1-9]$/.test(k) || ["x", " ", "w", "a", "s", "d", "f", "Shift"].includes(k);
        if (/^[1-8]$/.test(k)) { this.select(Number(k) - 1); return true; }
        if (k === "9") return true;
        if (k === "x") { this.drop(false); return true; }
        if (k === "f" && this.creative() && this.controlsPlayer()) { this.toggleFly(); return true; }
        if (teacher) {
            const cmd = {t: "time", m: "mobs", g: "gather", k: "kit", n: "mode", F9: "pause"}[k];
            if (cmd) { this.app.send({type: cmd}); return true; }
        }
        if ([" ", "w", "a", "s", "d", "Shift", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(k)) return this.controlsPlayer() || this.view === "free";
        return false;
    }

    cycleCamera() {  // V: your eyes, behind you, in front (the teacher: flying free too)
        const teacher = this.app.state.role !== "learner";
        const order = this.me !== null ? [...VIEWS, ...(teacher ? ["free"] : [])] : ["free"];
        const at = order.indexOf(this.view === "follow" ? "free" : this.view);
        this.setView(order[(at + 1) % order.length]);
    }

    setView(mode, watch = null) {
        if (mode === "free" && this.view !== "free") {
            const s = this.meState;
            this.free = s ? [s.x, s.y, s.z + 3] : this.free;
        }
        this.view = mode;
        this.watch = mode === "follow" ? watch : null;
        if (VIEWS.includes(mode) && this.app.keepPrefs) this.app.keepPrefs({camera: {mode}});
        this.app.updatePills();
    }

    // L: the camera follows the next learner in the world (round them all, then back)
    cycleWatch() {
        const people = [...this.names.entries()].filter(([id, n]) => n.kind === "player" && id !== this.me && this.latest.has(id)).map(([id]) => id);
        if (!people.length) { this.app.toast("Nobody else is in the world yet."); return; }
        const at = this.view === "follow" ? people.indexOf(this.watch) : -1;
        if (at + 1 >= people.length) { this.setView(this.me !== null ? "eyes" : "free"); this.app.toast("Camera: you"); return; }
        this.setView("follow", people[at + 1]);
        this.app.toast(`Camera: ${this.nameOf(people[at + 1])}  (L next, V view)`);
    }

    resetCamera() {
        this.setView(this.me !== null ? "eyes" : "free");
        this.pitch = -5;
        return true;
    }

    keyList() {
        // (craft_client.KEYS_TEXT, and the page's own: L, the panel's Tab)
        const rows = [["WASD", "walk"], ["Mouse", "look (click the game first)"], ["Space", "jump"], ["Shift", "run (held)"],
                      ["Ctrl", "Careful mode: you won't step off an edge"], ["Left button", "dig (held)"],
                      ["Right button", "place, or use the block or creature"], ["1-8, wheel", "the Toolbelt"], ["I", "the Backpack and blueprints"],
                      ["X", "throw one (Ctrl+X the stack)"], ["F", "fly in Sandbox (Space up, Ctrl down)"], ["V", "view"],
                      ["L", "watch the next learner"], ["B", "the Bot tab (Garage, Code, Brain)"], ["U", "upload the brain"], ["P", "autopilot"],
                      ["`", "the dev panel"], ["Esc", "the menu (or close a screen)"], ["Tab", "lessons"]];
        if (this.app.state.role !== "learner") rows.push(["T", "the time of day"], ["M", "creatures on or off"], ["G", "everyone to you"],
                                                        ["K", "a Bot kit for everyone"], ["N", "Sandbox or Challenge for everyone"], ["F9", "pause"]);
        rows.push(["H", "this list"]);
        return rows;
    }

    panelTabs(role) {
        const garage = !!(this.app.state.schemas && this.app.state.schemas.craftlab);
        if (role === "learner") return [...LEARNER_TABS.filter(([k]) => garage || k !== "garage"), ["camera", "Camera"], ["graphics", "Settings"], ["about", "Keys"]];
        return [["controls", "Controls"], ...TEACHER_TABS, ["camera", "Camera"], ["mission", "My mission"], ["graphics", "Graphics"], ["about", "About"]];
    }

    tabs() { return [["controls", "Controls"], ["camera", "Camera"]]; }

    pill() {
        const L = this.app.state.lesson;
        const mode = {survival: "challenge", creative: "sandbox"}[L && L.game_mode] || (L && L.game_mode) || "challenge";
        return L ? `Mission ${L.lesson_number} · ${mode.toUpperCase()} · ${L.time === "cycle" ? "day and night" : L.time}${this.paused ? " · PAUSED" : ""}` : "";
    }

    cameraPill() {
        return `Camera: ${VIEW_NAMES[this.view] || this.view}${this.view === "follow" && this.watch !== null ? " " + this.nameOf(this.watch) : ""} (V to change${this.app.state.role !== "learner" ? ", L to watch someone" : ""})`;
    }

    learnerHead() { return ["Player", "Health", "Holding"]; }

    learnerCells(p) {
        const esc = this.app.esc, id = [...this.names.entries()].find(([, n]) => n.kind === "player" && n.name === p.name);
        const e = id ? this.latest.get(id[0]) : null;
        return [e ? `${e.x.toFixed(0)}, ${e.y.toFixed(0)}, ${e.z.toFixed(0)}` : "", e ? `${e.hp} / 100` : "", e && e.held ? esc(sim.nameOf(e.held)) : ""];
    }

    renderTab(tab, body) {
        const app = this.app, S = app.state, L = S.lesson, esc = app.esc, send = app.send;
        if (tab === "controls") {
            if (!L) { body.innerHTML = "<p class='note'>Waiting for the lesson…</p>"; return true; }
            const R = L.rules || {}, hz = L.hazards || {};
            const on = (id, yes, a, b) => `<button id="${id}" class="${yes ? "on" : ""}">${yes ? a : b}</button>`;
            body.innerHTML = `
              ${app.missionRow()}
              <h2>The island</h2>
              <div class="row">
                <button id="cr-gather" class="go">EVERYONE TO ME</button>
                <button id="cr-kit">A BOT KIT FOR EVERYONE</button>
                <button id="cr-pause" class="${this.paused ? "on" : ""}">${this.paused ? "RESUME" : "PAUSE"}</button>
                <button id="cr-save">SAVE THE WORLD</button>
              </div>
              <div class="note">EVERYONE TO ME brings the class to where you stand (G); A BOT KIT gives everyone a Bot dock, Boards and Glowsticks (K); PAUSE stops the world (F9).</div>
              <div class="row"><label>Time of day</label>${TIMES.map(([k, t]) => `<button data-time="${k}" class="${(L.time || "cycle") === k ? "on" : ""}">${t}</button>`).join("")}</div>
              <div class="note">T moves it on (dawn, day, dusk, night, then the cycle again), as the window's.</div>
              <div class="row"><label>Learners play</label>${on("cr-mode", ["sandbox", "creative"].includes(L.game_mode), "SANDBOX: fly, every block, nothing hurts", "CHALLENGE")}</div>
              <div class="row"><label>Creatures</label>${on("cr-mobs", !!hz.mobs, "Glitch rifts at dusk, Rust Walkers", "No creatures")}</div>
              <div class="row"><label>Energy</label>${on("cr-energy", (hz.energy ?? hz.hunger) !== false && (R.energy ?? R.hunger) !== false, "Energy drains as you work", "Off")}</div>
              <div class="row"><label>Knocked out</label>${on("cr-keep", R.keep_items !== false, "You keep your things", "Your things stay where you fell")}</div>
              <div class="row"><label>Falls</label>${on("cr-falls", R.falls_hurt !== false, "A long fall hurts", "Falls don't hurt")}</div>
              <div class="row"><label>Overload Cells</label>${on("cr-blasts", !!R.blasts, "A Bot or a Glitch shard can arm them", "Off")}</div>
              <div class="row"><label>Teacher in the world</label>${on("cr-tplayer", L.teacher_player !== false, "Yes (Sandbox)", "No: watching")}</div>
              <div class="row"><label>Designs</label>${on("cr-lock", !!L.designs_locked, "Locked", "Learners may change their Bots")}</div>
              <h2>A new world</h2>
              <div class="row"><label>Seed</label><input id="cr-seed" placeholder="any number (blank: a new one)" style="width:12em">
                <select id="cr-size"><option value="small">small</option><option value="medium" selected>medium</option><option value="large">large</option></select>
                <button id="cr-new">${S.confirm === "newworld" ? "SURE? PRESS AGAIN" : "NEW WORLD FOR EVERYONE"}</button></div>
              <div class="note">The island now is kept as world_old on the class server; everyone's window and page is sent the new one.</div>
              ${app.restartRow()}`;
            const lessonSend = patch => send({type: "lesson", lesson: patch});
            app.wireMissionRow(body);
            $("cr-gather").onclick = () => send({type: "gather"});
            $("cr-kit").onclick = () => send({type: "kit"});
            $("cr-pause").onclick = () => send({type: "pause"});
            $("cr-save").onclick = () => send({type: "save_world"});
            body.querySelectorAll("button[data-time]").forEach(b => b.onclick = () => lessonSend({time: b.dataset.time}));
            $("cr-mode").onclick = () => send({type: "mode"});
            $("cr-mobs").onclick = () => send({type: "mobs"});
            const now = () => S.lesson || L;
            $("cr-energy").onclick = () => { const h = now().hazards || {}, v = (h.energy ?? h.hunger) === false; lessonSend({hazards: {energy: v}, rules: {energy: v}}); };
            $("cr-keep").onclick = () => lessonSend({rules: {keep_items: (now().rules || {}).keep_items === false}});
            $("cr-falls").onclick = () => lessonSend({rules: {falls_hurt: (now().rules || {}).falls_hurt === false}});
            $("cr-blasts").onclick = () => lessonSend({rules: {blasts: !(now().rules || {}).blasts}});
            $("cr-tplayer").onclick = () => lessonSend({teacher_player: now().teacher_player === false});
            $("cr-lock").onclick = () => lessonSend({designs_locked: !now().designs_locked});
            $("cr-new").onclick = () => app.twice("newworld", "SURE? PRESS AGAIN", () => {
                const seed = parseInt($("cr-seed").value, 10);
                send({type: "new_world", seed: Number.isFinite(seed) ? seed : 0, size: $("cr-size").value});
            });
            app.wireRestartRow(body);
            return true;
        }
        if (tab === "camera") {
            const people = [...this.names.entries()].filter(([id, n]) => n.kind === "player" && id !== this.me);
            const views = this.me !== null ? [...VIEWS, ...(S.role !== "learner" ? ["free"] : [])] : ["free"];
            body.innerHTML = `
              <h2>Camera</h2>
              <div class="row">${views.map(m => `<button data-view="${m}" class="${this.view === m ? "on" : ""}">${VIEW_NAMES[m]}</button>`).join("")}</div>
              <div class="note">V changes the view. Flying free: WASD, the mouse, Space up and Ctrl down (Shift: faster).</div>
              ${S.role !== "learner" ? `<h2>Watch someone</h2><div class="row">${people.map(([id, n]) => `<button data-watch="${id}" class="${this.view === "follow" && this.watch === id ? "on" : ""}">${esc(n.name)}</button>`).join("") || "<span class='note'>Nobody else in the world yet</span>"}</div>
                <div class="note">L watches the next learner in turn.</div>` : ""}`;
            body.querySelectorAll("button[data-view]").forEach(b => b.onclick = () => { this.setView(b.dataset.view); app.renderPanel(); });
            body.querySelectorAll("button[data-watch]").forEach(b => b.onclick = () => { this.setView("follow", Number(b.dataset.watch)); app.renderPanel(); });
            return true;
        }
        return false;
    }

    dispose() {
        this.disposed = true;
        const cv = this.app.canvas;
        this.capture(false);
        document.removeEventListener("mousemove", this.onMove);
        cv.removeEventListener("pointerdown", this.onDown);
        window.removeEventListener("pointerup", this.onUp);
        cv.removeEventListener("wheel", this.onWheel);
        cv.removeEventListener("contextmenu", this.onMenu);
        document.removeEventListener("pointerlockchange", this.onLock);
        window.removeEventListener("keydown", this.onKeyRaw);
        window.removeEventListener("keyup", this.onKeyUpRaw);
        window.removeEventListener("blur", this.onBlur);
        this.closeMenu(false);
        document.body.classList.remove("craftscreen");
        this.closeScreen(false);
        this.hud.clear();
        this.scene.dispose();
    }
}
