// Craft Lab in Club Coders Live (CHANGE 202): the island of blocks, its players, creatures, Craft Bots and things
// dropped, drawn from the class server's world and snapshots, and a learner (or the teacher, in the world in creative)
// playing on the page as in the window (craft/craft_client.py): your own player predicted as the window predicts it
// (craft_sim.js: craft_sim.py's step, ported line for line), digging and placing shown at once and the server's to keep.
//
// The world comes as the window's does: a world_head message, the blocks and their meta zipped in binary parts (kind 9,
// a two-byte index), then the world message; the page inflates them (the browser's own DecompressionStream), works the
// light out as craft_world does (the sky's straight down each open column and the torches', spread a level less a
// block) and meshes the chunks near the camera with craft_mesh.js (craft_mesh.py's open faces, corner shading and baked
// light, byte for byte), nearest first and a few milliseconds a frame, again where a block changes. The blocks' and
// items' tables and the atlas are craft.json and tex/craft_atlas.png (make_craft.py: craft_art's own atlas); the
// server's own blocks (mods/blocks.py) are painted into it here as the window paints them.
//
// The look is the window's on every tier (craft_gfx.py): Craft Lab's own shader (the atlas's pixels times the corner
// shading and the light baked into each corner, the sky's part of it times the time of day, the torches' warm and the
// same all night, fog into the sky's colour at the edge of the view; VIEW metres a tier: mesh 72, lines 96, blocks 64,
// low 80, medium 112, high 144, ultra 224), sun shadows from medium (a shadow map that follows you), waving leaves,
// plants and water on high and ultra, the sky's colour through the day, the sun and the moon crossing it, the stars at
// night, the clouds (low and up; two layers on ultra); mesh and lines are the engine's line looks (black faces, every
// face's edges on mesh, only the folds and where the block changes on lines, fading into the dark). The creatures,
// players, Craft Bots and things dropped are craft_models' boxes with the atlas's faces, lit by where they stand, their
// legs and arms swinging, a red flash when hurt, the armour each player wears (CHANGE 203: the roster's wear); the held
// item at the bottom right, the block you look at outlined, the crack as you dig, bits flying.

/* global BABYLON */

import {BaseScene, TIERS, v3, tierSettings, mulberry, applyResolution} from "./base3d.js";
import {CRAFT_FIELDS, KIND_SNAPSHOT, kindOf as frameKind, unpackSnapshot} from "./wire.js";
import * as sim from "./craft_sim.js";
import {Tables, meshChunk, CHUNK, CORNERS, FACE_SHADE, UV} from "./craft_mesh.js";
import {Predictor, InputLog, ErrorSmoother, LeadController, quantiseInput, packInput, seqDiff, SEQ_MASK} from "./predict.js";
import {CraftHud, CraftScreen, setAtlas, HOTBAR, iconTile} from "./craft_ui.js";
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
const CLOUDS = {mesh: 0, lines: 0, blocks: 0, low: 1, medium: 1, high: 1, ultra: 2};
const PARTICLES = {mesh: 6, lines: 6, blocks: 8, low: 10, medium: 14, high: 18, ultra: 24};
const SKY_DAY = [0.48, 0.68, 0.98], SKY_DUSK = [0.95, 0.55, 0.32], SKY_NIGHT = [0.015, 0.025, 0.07];
const VIEWS = ["eyes", "behind", "front"];
const VIEW_NAMES = {eyes: "your eyes", behind: "behind you", front: "in front of you", free: "flying free", follow: "following"};
const MOUSE_SPEED = 0.12;   // degrees a pixel
const PLACE_GAP = 0.22;
const TIMES = [["dawn", "Dawn"], ["day", "Day"], ["dusk", "Dusk"], ["night", "Night"], ["cycle", "Day and night"]];
const ARMOUR_TILES = {cloth: "cloth_armour", copper: "copper_block", iron: "iron_block", crystal: "crystal_block"};
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const wrapDeg = d => ((d + 180) % 360 + 360) % 360 - 180;

// ---------- the tables and the atlas (craft.json, tex/craft_atlas.png: make_craft.py) ----------
let dataPromise = null;
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
        ]).then(([data, img]) => ({data, img}));
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

// ---------- the time of day (craft_gfx.time_look) ----------
export function timeLook(t) {
    const a = t * 2 * Math.PI, sunUp = Math.sin(a);
    const day = clamp(sunUp * 3 + 0.35, 0, 1), daylight = 0.14 + 0.86 * day;
    const dusk = Math.cos(a) !== 0 ? Math.max(0, 1 - Math.abs(sunUp) * 4) : 0;
    let sky = SKY_NIGHT.map((v, i) => v + (SKY_DAY[i] - v) * day);
    sky = sky.map((v, i) => v + (SKY_DUSK[i] - v) * dusk * 0.6);
    let d = [Math.cos(a) * 0.9, 0.35, Math.sin(a)];
    const l = Math.hypot(...d);
    d = d.map(v => v / l);
    const tint = daylight > 0.6 ? [1, 1, 1] : [0.75 + 0.25 * daylight, 0.8 + 0.2 * daylight, 1.0];
    return {daylight, sky, sunDir: d, tint};
}

// ---------- the shaders (craft_gfx's, in Babylon's axes: the game's z is Babylon's y) ----------
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
varying vec2 vUV;
varying vec3 vLight;
varying float vDist;
varying float vSunny;
#ifdef SHADOWS
uniform mat4 shadowMatrix;
varying vec4 vShadow;
#endif
void main(void) {
    vec4 p = world * vec4(position, 1.0);
    float flags = floor(cdata.a * 255.0 + 0.5);
    if (u_wave > 0.5 && mod(flags, 32.0) >= 16.0) {
        float gx = p.x + sin(u_time * 1.7 + p.z * 0.9 + p.y) * 0.04;
        p.z += cos(u_time * 1.3 + gx * 0.8) * 0.04;
        p.x = gx;
    }
    gl_Position = viewProjection * p;
    vUV = uv;
    float sky = pow(0.8, (1.0 - cdata.g) * 15.0) * u_day;
    float blk = cdata.b > 0.01 ? pow(0.8, (1.0 - cdata.b) * 15.0) : 0.0;
    vec3 l = max(vec3(sky) * u_tint, vec3(blk, blk * 0.86, blk * 0.62));
    vLight = max(l, vec3(0.045)) * cdata.r;
    vSunny = cdata.g * u_day;
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
uniform vec4 baseColor;
varying vec2 vUV;
varying vec3 vLight;
varying float vDist;
varying float vSunny;
#ifdef SHADOWS
uniform highp sampler2DShadow shadowMap;
uniform float shadowBias;
varying vec4 vShadow;
#endif
void main(void) {
    vec4 t = texture2D(atlas, vUV);
    if (t.a < u_cut) discard;
    vec3 c = t.rgb * vLight;
#ifdef SHADOWS
    vec3 sc = vShadow.xyz / vShadow.w;
    vec2 suv = sc.xy * 0.5 + 0.5;
    float lit = 1.0;
    if (suv.x > 0.0 && suv.x < 1.0 && suv.y > 0.0 && suv.y < 1.0 && sc.z < 1.0) lit = texture(shadowMap, vec3(suv, sc.z * 0.5 + 0.5 - shadowBias));
    c *= 1.0 - 0.36 * (1.0 - lit) * clamp(vSunny * 1.4 - 0.25, 0.0, 1.0);
#endif
    float f = clamp((vDist - u_fog.x) / (u_fog.y - u_fog.x), 0.0, 1.0);
    gl_FragColor = vec4(mix(c, u_fog_colour, f), t.a * u_alpha) * baseColor;
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
varying vec2 vUV;
varying vec3 vLight;
varying vec4 vCol;
varying float vDist;
void main(void) {
    vec4 p = world * vec4(position, 1.0);
    gl_Position = viewProjection * p;
    vUV = uv;
    float sky = pow(0.8, (1.0 - u_here.x) * 15.0) * u_day;
    float blk = u_here.y > 0.01 ? pow(0.8, (1.0 - u_here.y) * 15.0) : 0.0;
    vLight = max(max(vec3(sky) * u_tint, vec3(blk, blk * 0.86, blk * 0.62)), vec3(0.06));
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

function register() {
    const S = BABYLON.Effect.ShadersStore;
    if (S.craftChunkVertexShader) return;
    S.craftChunkVertexShader = CHUNK_VERT; S.craftChunkFragmentShader = CHUNK_FRAG;
    S.craftEntVertexShader = ENT_VERT; S.craftEntFragmentShader = ENT_FRAG;
    S.craftDepthVertexShader = DEPTH_VERT; S.craftDepthFragmentShader = DEPTH_FRAG;
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

// ---------- the scene ----------
export class CraftScene extends BaseScene {
    static TIERS = TIERS;  // (every tier, as the window's craft_gfx)
    static TIER_TEXT = {
        mesh: "mesh: black, and every block face's edges in one colour, the lines behind hidden.",
        lines: "lines: black, the blocks' outlines in one colour (only where the surface folds or the block changes), fading into the dark.",
        blocks: "blocks: Craft Lab's own look nearest you (64 metres), no clouds or shadows: the floor every machine draws.",
        low: "low: 80 metres of the island, the clouds.",
        medium: "medium: 112 metres, the sun's shadows.",
        high: "high: 144 metres, sharper shadows, the leaves, plants and water moving in the wind.",
        ultra: "ultra: for a strong graphics card: 224 metres of the island, soft shadows reaching far, two layers of clouds."};

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
                       "u_cut", "u_alpha", "baseColor", "shadowMatrix", "shadowBias"],
            samplers: ["atlas", "shadowMap"], defines, needAlphaBlending: blend});
        m.setTexture("atlas", this.atlasTex);
        m.setFloat("u_cut", cut);
        m.setFloat("u_alpha", alpha);
        m.setColor4("baseColor", new BABYLON.Color4(1, 1, 1, 1));
        m.backFaceCulling = cull;
        if (blend) { m.disableDepthWrite = true; m.alphaMode = BABYLON.Constants.ALPHA_COMBINE; }
        if (this.rtt) {
            m.setInternalTexture("shadowMap", this.rtt.depthStencilTexture);
            m.setFloat("shadowBias", SHADOW_BIAS);
        }
        (this.shaded || (this.shaded = [])).push(m);
        return m;
    }

    entMaterial(name) {
        const m = new BABYLON.ShaderMaterial(name, this.scene, {vertex: "craftEnt", fragment: "craftEnt"}, {
            attributes: ["position", "uv", "color"],
            uniforms: ["world", "viewProjection", "cameraPosition", "u_day", "u_tint", "u_here", "u_fog_colour", "u_fog", "u_flash", "baseColor"],
            samplers: ["atlas"], needAlphaBlending: false});
        m.setTexture("atlas", this.atlasTex);
        m.setColor4("baseColor", new BABYLON.Color4(1, 1, 1, 1));
        m.backFaceCulling = false;
        const engine = this.engine, here = new BABYLON.Vector2(1, 0), flash = new BABYLON.Vector4(1, 0.15, 0.15, 0);
        m.onBindObservable.add(mesh => {  // (each model's own light where it stands, and its red flash: craft_gfx.set_here, flash)
            const e = engine._currentEffect || m.getEffect();
            if (!e) return;
            const h = mesh && mesh.ccHere;
            here.set(h ? h[0] : 1, h ? h[1] : 0);
            flash.w = h && h[2] ? 0.55 : 0;
            e.setVector2("u_here", here);
            e.setVector4("u_flash", flash);
        });
        (this.shaded || (this.shaded = [])).push(m);
        return m;
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
        this.depthMat.backFaceCulling = false;
        scene.customRenderTargets.push(rtt);
        this.shadowMatrix = BABYLON.Matrix.Identity();
        this.shadowArea = area;
    }

    // the sun and the moon (squares crossing the sky), the stars at night, the clouds (craft_gfx.Sky): the sky's
    // things drawn first, round the camera, at the same size to the eye as the window's
    makeSky() {
        const scene = this.scene, root = new BABYLON.TransformNode("sky", scene);
        const far = this.camera.maxZ * 0.8, k = far / 250;
        const flat = (name, rgb, alpha = 1) => {
            const m = new BABYLON.StandardMaterial(name, scene);
            m.disableLighting = true;
            m.emissiveColor = new BABYLON.Color3(rgb[0], rgb[1], rgb[2]);
            m.backFaceCulling = false;
            m.disableDepthWrite = true;
            if (alpha < 1) m.alpha = alpha;
            return m;
        };
        const sun = BABYLON.MeshBuilder.CreatePlane("sun", {size: 14 * k}, scene);
        sun.material = flat("sunmat", [1.0, 0.95, 0.6]);
        const moon = BABYLON.MeshBuilder.CreatePlane("moon", {size: 10 * k}, scene);
        moon.material = flat("moonmat", [0.85, 0.88, 1.0]);
        for (const m of [sun, moon]) { m.billboardMode = BABYLON.Mesh.BILLBOARDMODE_ALL; m.parent = root; m.renderingGroupId = 0; m.isPickable = false; }
        const rnd = mulberry(3), gauss = () => Math.sqrt(-2 * Math.log(Math.max(1e-9, rnd()))) * Math.cos(2 * Math.PI * rnd());
        const spos = [], scol = [];
        for (let i = 0; i < 500; i++) {
            let d = [gauss(), gauss(), Math.abs(gauss()) + 0.05];
            const l = Math.hypot(...d);
            d = d.map(v => v / l * 300 * k);
            spos.push(d[0], d[2], d[1]);
            const b = 0.5 + rnd() * 0.5;
            scol.push(b, b, b, 1);
        }
        const stars = new BABYLON.Mesh("stars", scene), vd = new BABYLON.VertexData();
        vd.positions = spos;
        vd.colors = scol;
        vd.indices = Array.from({length: 500}, (_, i) => i);
        vd.applyToMesh(stars);
        const sm = flat("starmat", [1, 1, 1]);
        sm.pointsCloud = true;
        sm.pointSize = 2;
        sm.emissiveColor = new BABYLON.Color3(0, 0, 0);
        sm.disableLighting = true;
        sm.diffuseColor = new BABYLON.Color3(0, 0, 0);
        stars.useVertexColors = true;
        sm.emissiveColor = new BABYLON.Color3(1, 1, 1);
        stars.material = sm;
        stars.parent = root;
        stars.renderingGroupId = 0;
        stars.hasVertexAlpha = false;
        const clouds = [], crnd = mulberry(5);
        for (let layer = 0; layer < (CLOUDS[this.tier] || 0); layer++) {
            const size = 40, cell = 12;
            let field = Array.from({length: size}, () => Array.from({length: size}, () => crnd()));
            for (let r = 0; r < 3; r++) {
                field = field.map((row, i) => row.map((v, j) => (v + field[(i + 1) % size][j] + field[(i + size - 1) % size][j] +
                    row[(j + 1) % size] + row[(j + size - 1) % size]) / 5));
            }
            const flatF = field.flat(), lo = Math.min(...flatF), hi = Math.max(...flatF);
            const pos = [], idx = [], a = layer === 0 ? 0.75 : 0.5;
            for (let i = 0; i < size; i++) for (let j = 0; j < size; j++) {
                if ((field[i][j] - lo) / Math.max(1e-6, hi - lo) < 0.56) continue;
                const x0 = (i - size / 2) * cell, y0 = (j - size / 2) * cell, n = pos.length / 3;
                pos.push(x0, 0, y0, x0 + cell, 0, y0, x0 + cell, 0, y0 + cell, x0, 0, y0 + cell);
                idx.push(n, n + 2, n + 1, n, n + 3, n + 2);
            }
            const m = new BABYLON.Mesh("clouds", scene), cv = new BABYLON.VertexData();
            cv.positions = pos;
            cv.indices = idx;
            cv.applyToMesh(m);
            const cm = flat("cloudmat" + layer, [1, 1, 1], a);
            m.material = cm;
            m.position.y = 78 + layer * 14;
            m.renderingGroupId = 1;
            m.isPickable = false;
            m.alphaIndex = 100;
            clouds.push(m);
        }
        return {root, sun, moon, stars, starMat: sm, clouds, drift: 0, far};
    }

    // the block you look at (a thin outline) and the crack drawn over it as you dig (craft_gfx.Target)
    makeTarget() {
        const scene = this.scene, e = 0.002, lo = -e, hi = 1 + e, L = [];
        const c = [[lo, lo, lo], [hi, lo, lo], [hi, hi, lo], [lo, hi, lo], [lo, lo, hi], [hi, lo, hi], [hi, hi, hi], [lo, hi, hi]];
        for (const [a, b] of [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]]) {
            L.push([v3(...c[a]), v3(...c[b])]);
        }
        const box = BABYLON.MeshBuilder.CreateLineSystem("target", {lines: L}, scene);
        box.color = this.wire ? new BABYLON.Color3(1, 1, 1) : new BABYLON.Color3(0.05, 0.05, 0.05);
        box.alpha = this.wire ? 1 : 0.85;
        if (box.material && box.material.setColor4) box.material.setColor4("baseColor", new BABYLON.Color4(1, 1, 1, 1));  // (an opaque canvas's check)
        box.isPickable = false;
        box.renderingGroupId = 1;
        box.setEnabled(false);
        const geo = {pos: [], uv: [], idx: []};
        const ce = 0.004;
        for (let d = 0; d < 6; d++) {
            const n = geo.pos.length / 3;
            CORNERS[d].forEach((k, q) => {
                const p = k.map(v => (v - 0.5) * (1 + 2 * ce) + 0.5);
                geo.pos.push(p[0], p[2], p[1]);
                geo.uv.push(UV[q][0], UV[q][1]);
            });
            geo.idx.push(n, n + 2, n + 1, n, n + 3, n + 2);
        }
        const crack = new BABYLON.Mesh("crack", scene), vd = new BABYLON.VertexData();
        vd.positions = geo.pos;
        vd.uvs = geo.uv;
        vd.indices = geo.idx;
        vd.applyToMesh(crack, true);
        const m = new BABYLON.StandardMaterial("crackmat", scene);
        m.diffuseTexture = this.atlasTex;
        m.useAlphaFromDiffuseTexture = true;
        m.disableLighting = true;
        m.emissiveColor = new BABYLON.Color3(1, 1, 1);
        m.backFaceCulling = false;
        m.zOffset = -2;
        crack.material = m;
        crack.renderingGroupId = 1;
        crack.isPickable = false;
        crack.setEnabled(false);
        return {box, crack, stage: -1, unit: geo.uv.slice()};
    }

    showTarget(block, progress) {
        const T = this.target;
        if (!T) return;
        if (!block) { T.box.setEnabled(false); T.crack.setEnabled(false); return; }
        T.box.position = v3(block[0], block[1], block[2]);
        T.box.setEnabled(true);
        if (progress <= 0) { T.crack.setEnabled(false); return; }
        const stage = Math.min(9, Math.floor(progress * 10));
        T.crack.position = v3(block[0], block[1], block[2]);
        T.crack.setEnabled(true);
        if (stage !== T.stage) {
            T.stage = stage;
            const [u0, v0, s] = uvOf(this.atlas.where, `crack_${stage}`);
            T.crack.updateVerticesData(BABYLON.VertexBuffer.UVKind, T.unit.map((v, i) => (i % 2 ? v0 : u0) + v * s));
        }
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
            if (m.name.startsWith("craft") && !m.name.startsWith("craftent")) m.setFloat("u_wave", WAVES.has(this.tier) ? 1 : 0);
        }
        const S = this.sky;
        if (S) {
            const d = L.sunDir, far = S.far * 0.98;
            S.sun.position = v3(d[0] * far, d[1] * far, d[2] * far);
            S.moon.position = v3(-d[0] * far, -d[1] * far, -d[2] * far);
            const night = clamp(-d[2] * 4 + 0.2, 0, 1);
            S.stars.setEnabled(night > 0.02);
            S.starMat.alpha = night;
            S.starMat.emissiveColor = new BABYLON.Color3(night, night, night);
            const day = clamp(d[2] * 3 + 0.4, 0, 1), g = 0.1 + 0.9 * day;
            for (const c of S.clouds) c.material.emissiveColor = new BABYLON.Color3(g, g, g * 1.02);
        }
    }

    // ---------- every frame ----------
    // the waving leaves' clock, the sun's shadow over the camera, the sky round it, the clouds drifting (craft_gfx.tick)
    tick(dt, cam) {
        this.waveT += dt;
        if (WAVES.has(this.tier)) for (const m of this.shaded || []) m.setFloat("u_time", this.waveT);
        const camB = this.camera.position;
        if (this.sky) {
            this.sky.root.position.copyFrom(camB);
            this.sky.drift = (this.sky.drift + dt * 1.2) % 12.0;
            this.sky.clouds.forEach((c, k) => {
                c.position.x = Math.floor(cam[0] / 12) * 12 + this.sky.drift * (1 + k * 0.5);
                c.position.z = Math.floor(cam[1] / 12) * 12;
            });
        }
        if (this.rtt && this.timeLook) {
            let d = this.timeLook.sunDir;
            if (d[2] < 0.05) d = d.map(v => -v);  // (the sun below the horizon: the moon's light, from above)
            const target = new BABYLON.Vector3(cam[0], cam[2], cam[1]);
            this.sunCam.position = target.add(new BABYLON.Vector3(d[0] * 120, d[2] * 120, d[1] * 120));
            this.sunCam.setTarget(target);
            this.sunCam.computeWorldMatrix(true);
            this.shadowMatrix.copyFrom(this.sunCam.getViewMatrix(true).multiply(this.sunCam.getProjectionMatrix(true)));
            for (const m of this.shaded || []) if (m.name !== "craftent") m.setMatrix("shadowMatrix", this.shadowMatrix);
            // (what casts: the chunks round you, the players and creatures)
            const r = this.shadowArea / 2 + CHUNK * 1.5, list = [];
            for (const [key, ch] of this.chunks) {
                if (Math.hypot(ch.cx - cam[0], ch.cy - cam[1]) < r) for (const m of ch.casters) list.push(m);
            }
            for (const md of this.models.values()) for (const m of md.meshes) list.push(m);
            this.rtt.renderList = list;
            for (const m of list) if (!m.ccDepth) { this.rtt.setMaterialForRendering(m, this.depthMat); m.ccDepth = true; }
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

    // ---------- particles (craft_gfx.Particles) ----------
    burst(x, y, z, tile, n = null, speed = 2.5) {
        if (!this.atlas) return;
        n = n || PARTICLES[this.tier] || 12;
        const [u0, v0, s] = uvOf(this.atlas.where, tile || "particle"), rnd = Math.random;
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

    // the light where a thing stands: the sky's and the torches' (0 to 1), and whether it flashes
    hereAt(x, y, z) {
        const w = this.world;
        const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z + 0.5);
        if (!w || !w.inside(xi, yi, zi)) return [1, 0, 0];
        const i = w.at(xi, yi, zi);
        return [w.sky[i] / 15, w.glow[i] / 15, 0];
    }

    drawCalls() { return this.scene ? this.scene.getActiveMeshes().length : 0; }

    stats() {  // (the tests and the Graphics tab)
        let meshes = 0, lines = 0;
        for (const ch of this.chunks.values()) for (const m of ch.meshes) (m.material && m.material.ccLine ? lines++ : meshes++);
        return {chunks: this.chunks.size, todo: this.todo.size, meshes, lines, models: this.models.size, built: this.built};
    }
}

// ---------- people, creatures and Craft Bots (craft_models.py) ----------
const faces = (front, other) => [other, other, front, other, other, other];
const rgb01 = c => (c && c.length >= 3 ? c.slice(0, 3).map(v => clamp(v / 255, 0, 1)) : [0.9, 0.9, 0.9]);

class Model {
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
        this.here = [1, 0, 0];
        this.worn = [0, 0, 0, 0];
        this.armour = [];
        const c = rgb01(colour);
        ({player: () => this.buildPlayer(c), rust: () => this.buildPlayer(c, true), fluff: () => this.buildFluff(),
          bleep: () => this.buildBleep(), glitch: () => this.buildGlitch(), bot: () => this.buildBot()}[kind] || (() => this.buildPlayer(c)))();
        if (kind === "rust") this.body.scaling.setAll(1.06);
        this.tag = null;
        this.name = name;
        if (name) this.makeTag(name);
    }

    node(parent, pivot) {
        const n = new BABYLON.TransformNode("joint", this.sc.scene);
        n.parent = parent;
        n.position = v3(...pivot);
        return n;
    }

    box(parent, lo, hi, tiles, colour) {
        const m = this.sc.part(this.kind, boxGeo(this.sc.atlas.where, [[lo, hi, tiles, colour]]), parent, this);
        m.ccHere = this.here;
        return m;
    }

    limb(parent, pivot, lo, hi, tiles, colour) {
        const j = this.node(parent, pivot);
        this.box(j, lo, hi, tiles, colour);
        return j;
    }

    buildPlayer(c, rust = false) {
        const top = rust ? "rust_face" : "player_face", shirt = rust ? "rust_body" : "shirt", legs = rust ? "rust_body" : "trousers";
        const tint = rust ? [0.95, 0.75, 0.6] : c;
        this.legs = [-0.12, 0.12].map(x => this.limb(this.body, [x, 0, 0.72], [-0.12, -0.12, -0.72], [0.12, 0.12, 0], legs, [0.9, 0.9, 0.9]));
        this.box(this.body, [-0.24, -0.12, 0.72], [0.24, 0.12, 1.38], shirt, tint);
        const arm = rust ? "rust_body" : "skin";
        this.arms = [-0.36, 0.36].map(x => this.limb(this.body, [x, 0, 1.36], [-0.11, -0.11, -0.64], [0.11, 0.11, 0], arm, [1, 1, 1]));
        this.head = this.node(this.body, [0, 0, 1.38]);
        this.box(this.head, [-0.24, -0.24, 0], [0.24, 0.24, 0.48], faces(top, rust ? "rust_body" : "hair"), [1, 1, 1]);
    }

    buildFluff() {
        for (const x of [-0.22, 0.22]) for (const y of [-0.3, 0.3]) this.legs.push(this.limb(this.body, [x, y, 0.4], [-0.09, -0.09, -0.4], [0.09, 0.09, 0], "soil", [0.9, 0.85, 0.8]));
        this.box(this.body, [-0.34, -0.48, 0.38], [0.34, 0.42, 0.98], "fluff_wool", [1, 1, 1]);
        this.head = this.node(this.body, [0, 0.42, 0.78]);
        this.box(this.head, [-0.2, 0, -0.18], [0.2, 0.36, 0.22], faces("fluff_face", "fluff_wool"), [1, 1, 1]);
    }

    buildBleep() {
        this.legs = [-0.28, 0.28].map(x => this.limb(this.body, [x, 0, 0.16], [-0.05, -0.16, -0.16], [0.05, 0.16, 0.16], "corestone", [0.7, 0.7, 0.75]));
        this.box(this.body, [-0.24, -0.24, 0.12], [0.24, 0.24, 0.52], "bleep_body", [1, 1, 1]);
        this.head = this.node(this.body, [0, 0, 0.52]);
        this.box(this.head, [-0.2, -0.2, 0], [0.2, 0.2, 0.32], faces("bleep_face", "bleep_body"), [1, 1, 1]);
        this.box(this.head, [-0.02, -0.02, 0.32], [0.02, 0.02, 0.5], "iron_block", [1, 1, 1]);
        this.box(this.head, [-0.05, -0.05, 0.5], [0.05, 0.05, 0.58], "lumen", [1, 1, 1]);
    }

    buildGlitch() {
        this.box(this.body, [-0.44, -0.44, 0], [0.44, 0.44, 0.88], faces("glitch_face", "glitch_body"), [1, 1, 1]);
    }

    buildBot() {  // a Craft Bot: Club Coders' own little robot, its yellow face and a dock-coloured body
        this.legs = [-0.34, 0.34].map(x => this.limb(this.body, [x, 0, 0.2], [-0.07, -0.2, -0.2], [0.07, 0.2, 0.2], "corestone", [0.8, 0.8, 0.8]));
        this.box(this.body, [-0.3, -0.3, 0.14], [0.3, 0.3, 0.68], "dock_side", [1, 1, 1]);
        this.arms = [-0.37, 0.37].map(x => this.limb(this.body, [x, 0.0, 0.6], [-0.06, -0.06, -0.36], [0.06, 0.06, 0], "iron_block", [1, 1, 1]));
        this.head = this.node(this.body, [0, 0, 0.68]);
        this.box(this.head, [-0.26, -0.26, 0], [0.26, 0.26, 0.4], faces("bot_face", "copper_block"), [1, 1, 1]);
        this.box(this.head, [-0.03, -0.03, 0.4], [0.03, 0.03, 0.6], "iron_block", [1, 1, 1]);
        this.box(this.head, [-0.06, -0.06, 0.6], [0.06, 0.06, 0.7], "lumen", [1, 1, 1]);
    }

    // (CHANGE 203, craft_models.Model.wear) the armour a person wears: boxes a little bigger than the parts
    wear(ids) {
        ids = [...(ids || []), 0, 0, 0, 0].slice(0, 4).map(v => v | 0);
        if (this.kind !== "player" || ids.join() === this.worn.join()) return;
        this.worn = ids;
        for (const m of this.armour) m.dispose();
        this.armour = [];
        const piece = (parent, lo, hi, tile) => {
            this.armour.push(this.box(parent, lo, hi, tile, [1, 1, 1]));
        };
        ids.forEach((id, part) => {
            const it = sim.B.items.get(id);
            if (!it || it.armour !== part) return;
            const tile = ARMOUR_TILES[it.key.split("_")[0]] || "iron_block";
            if (part === 0) piece(this.head, [-0.27, -0.27, 0.24], [0.27, 0.27, 0.53], tile);
            else if (part === 1) {
                piece(this.body, [-0.26, -0.14, 0.74], [0.26, 0.14, 1.40], tile);
                for (const arm of this.arms) piece(arm, [-0.125, -0.125, -0.3], [0.125, 0.125, 0.02], tile);
            } else if (part === 2) {
                piece(this.body, [-0.26, -0.14, 0.62], [0.26, 0.14, 0.8], tile);
                for (const leg of this.legs) piece(leg, [-0.135, -0.135, -0.5], [0.135, 0.135, 0.0], tile);
            } else for (const leg of this.legs) piece(leg, [-0.14, -0.15, -0.74], [0.14, 0.15, -0.5], tile);
        });
        this.meshes = this.meshes.filter(m => !m.isDisposed());
    }

    makeTag(text) {
        if (this.tag) this.tag.dispose();
        const t = this.tag = this.sc.makeLabel(text, "#ffffff", Math.max(1.0, Math.min(3.2, 0.2 * String(text).length + 0.5)));
        t.parent = this.root;
        t.position = v3(0, 0, this.kind === "bot" ? 1.62 : 2.15);
        t.renderingGroupId = 1;
        if (this.sc.wire) this.sc.lettering(t);
        this.tagText = text;
    }

    say(text) {  // a speech bubble (a Craft Bot's "say"), or back to the name with null
        const words = text || this.name;
        if (words && words !== this.tagText) this.makeTag(words);
    }

    // placed and posed from a record (craft_sim's: x, y, z, vx, vy, vz, yaw, pitch, flags)
    update(s, dt) {
        this.root.position = v3(s.x, s.y, s.z);
        this.root.rotation.y = -(s.yaw - 90) * DEG;
        const speed = Math.hypot(s.vx || 0, s.vy || 0);
        this.phase += dt * speed * 3.2;
        const a = Math.sin(this.phase) * Math.min(1, speed / 3) * 38;
        this.legs.forEach((leg, k) => { leg.rotation.x = -(k % 2 === 0 ? a : -a) * DEG; });
        if ((s.flags || 0) & sim.F_SWING) this.swing = 0.3;
        this.swing = Math.max(0, this.swing - dt);
        this.arms.forEach((arm, k) => {
            let p = k === 0 ? -a * 0.8 : a * 0.8;
            if (k === 1 && this.swing > 0) p = -70 * Math.sin(this.swing / 0.3 * Math.PI);
            if (this.kind === "rust") p -= 70;
            arm.rotation.x = -p * DEG;
        });
        if (this.head) this.head.rotation.x = this.kind === "player" ? -clamp(s.pitch || 0, -60, 60) * DEG : 0;
        if (this.kind === "glitch") {  // (it squashes as it lands and stretches as it leaps)
            const k = clamp((s.vz || 0) * 0.04, -0.25, 0.25);
            this.body.scaling = new BABYLON.Vector3(1 - k * 0.5, 1 + k, 1 - k * 0.5);
        }
        if ((s.flags || 0) & sim.F_SLEEP) {
            this.root.rotation.z = -90 * DEG;
            this.root.position.y = s.z + 0.3;
        } else this.root.rotation.z = 0;
        this.body.position.y = (s.flags || 0) & sim.F_SNEAK ? -0.25 : 0;
        const h = this.sc.hereAt(s.x, s.y, s.z);
        this.here[0] = h[0];
        this.here[1] = h[1];
        this.here[2] = (s.flags || 0) & sim.F_HURT ? 1 : 0;
    }

    dispose() {
        if (this.tag) this.tag.dispose();
        this.root.dispose();
    }
}

class ItemModel {  // a thing dropped: its little cube or card, turning and bobbing
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
        this.mods = ["mods/blocks.py", "mods/recipes.py", "mods/world.py", "mods/rules.py", "mods/bots/<username>.py"];
        this.scene = new CraftScene(app.canvas, app.tier, app.engine);
        this.controlKind = "craft";
        this.hud = new CraftHud();
        this.hud.onSelect = i => this.select(i);
        this.world = null;
        this.me = null;
        this.inventory = null;
        this.screen = null;
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
        this.sprintLock = false;
        this.jumpAt = -1; this.wAt = -1;
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
            if (this.screen || e.pointerType === "touch") return;
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
                this.placeAt = 0;  // (a click places at once; holding repeats)
            }
        };
        this.onUp = e => {
            if (e.button === 0) this.mouse.left = false;
            if (e.button === 2) this.mouse.right = false;
        };
        this.onWheel = e => {
            if (this.screen || !this.app.state.connected) return;
            e.preventDefault();
            if (this.inventory && this.controlsPlayer()) this.select((this.inventory.selected + (e.deltaY > 0 ? 1 : -1) + HOTBAR) % HOTBAR);
        };
        this.onLock = () => {
            this.captured = document.pointerLockElement === cv;
            if (!this.captured) this.mouse.left = this.mouse.right = false;
        };
        this.onMenu = e => e.preventDefault();
        this.onKeyRaw = e => {  // (Ctrl+Q: the window's drop the stack; Keys passes no key with Ctrl held)
            if ((e.key === "q" || e.key === "Q") && e.ctrlKey && this.app.state.connected && !this.screen) { e.preventDefault(); this.drop(true); }
        };
        document.addEventListener("mousemove", this.onMove);
        cv.addEventListener("pointerdown", this.onDown);
        window.addEventListener("pointerup", this.onUp);
        cv.addEventListener("wheel", this.onWheel, {passive: false});
        cv.addEventListener("contextmenu", this.onMenu);
        document.addEventListener("pointerlockchange", this.onLock);
        window.addEventListener("keydown", this.onKeyRaw);
    }

    capture(on) {
        const cv = this.app.canvas;
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
            this.app.toast("Teacher: T the time of day, M creatures, G everyone to you, K a Bot kit for everyone, N creative or survival, F9 pause", false, 8000);
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
        for (const k of ["hp", "food", "held"]) this.predictor.state[k] = state[k];  // (the server's own: never predicted)
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
    // and the buttons (jump, sprint, sneak, fly). play.js calls it with the keys, a pad (or the touch controls)
    keysInput(K, pad, tapped) {
        const flyB = this.fly && this.creative() ? sim.FLY_B : 0;
        if (this.screen || !this.controlsPlayer() || K.typing()) return {throttle: 0, steer: 0, buttons: flyB};
        if (this.demo === "walk") {  // (the tests: walk in a slow circle, jumping now and then: craft_client.demo_input)
            const t = performance.now() / 1000, yr = (90 + t * 12) * DEG;
            return {throttle: Math.cos(yr) * 0.6, steer: Math.sin(yr) * 0.6, buttons: Math.floor(t * 2) % 5 === 0 ? sim.JUMP_B : 0};
        }
        let f = (K.is("w", "ArrowUp") ? 1 : 0) - (K.is("s", "ArrowDown") ? 1 : 0);
        let r = (K.is("d", "ArrowRight") ? 1 : 0) - (K.is("a", "ArrowLeft") ? 1 : 0);
        let bt = 0;
        if (K.is(" ")) bt |= sim.JUMP_B;
        if (K.is("Shift")) bt |= sim.SNEAK_B;
        if (this.sprintLock) bt |= sim.SPRINT_B;
        if (f <= 0) this.sprintLock = false;
        if (pad) {
            if (!f && !r) { f = pad.y || 0; r = pad.x || 0; }
            if (pad.held.has("south")) bt |= sim.JUMP_B;
            if (pad.held.has("rb")) bt |= sim.SPRINT_B;
            if (pad.held.has("lb")) bt |= sim.SNEAK_B;
            if (pad.rx) this.yaw = ((this.yaw - pad.rx * 3.0) % 360 + 360) % 360;
            if (pad.ry) this.pitch = clamp(this.pitch + pad.ry * 2.0, -89, 89);
            if (pad.pressed.has("north")) this.toggleInventory();
            if (pad.pressed.has("west")) this.drop(false);
            if (pad.pressed.has("fly")) this.toggleFly();
            if (pad.pressed.has("inv")) this.toggleInventory();
            if (pad.pressed.has("drop")) this.drop(false);
            pad.pressed = new Set();
        }
        if (this.fly && this.creative()) bt |= sim.FLY_B;
        else this.fly = false;
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
        this.act({type: "select", slot: i});
    }

    drop(all) {
        if (!this.screen && this.controlsPlayer()) this.act({type: "drop", all});
    }

    toggleFly() {
        if (!this.creative()) return;
        this.fly = !this.fly;
        this.hud.say(this.fly ? "Flying" : "Walking", performance.now(), 1.5);
    }

    toggleInventory() {
        if (this.screen) { this.act({type: "close"}); this.closeScreen(); return; }
        if (!this.controlsPlayer() || !this.inventory) return;
        this.openScreen({...this.inventory, open: null});
    }

    openScreen(msg) {
        if (this.screen) this.screen.destroy();
        this.screen = new CraftScreen(msg, m => this.act(m), () => this.app.keys.down.has("Shift"));
        this.capture(false);
        this.mouse.left = this.mouse.right = false;
    }

    closeScreen(relock = true) {
        if (this.screen) { this.screen.destroy(); this.screen = null; }
        if (relock) this.capture(true);
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
        if (this.screen || !this.controlsPlayer() || !this.world) { this.digAt = null; sc.showTarget(null, 0); return; }
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
        const length = (this.gameRules || {}).day_length || 1200;
        if ((this.gameRules || {}).time_runs !== false && !this.paused) this.dayT = (this.dayT + dt / length) % 1.0;
        if (now - this.lookAt > 100 && this.controlsPlayer()) {
            this.lookAt = now;
            this.app.send({type: "look", yaw: Math.round(this.yaw * 10) / 10, pitch: Math.round(this.pitch * 10) / 10});
        }
        if (!this.world || !sc.mats) {
            sc.setTime(this.dayT);
            this.hud.update({now, hidden: true, title: this.titleText(), debug: this.world ? "" : "Craft Lab: the world is on its way…"});
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
            const K = this.app.keys, typing = K.typing() || this.screen;
            const f = typing ? 0 : (K.is("w", "ArrowUp") ? 1 : 0) - (K.is("s", "ArrowDown") ? 1 : 0);
            const r = typing ? 0 : (K.is("d", "ArrowRight") ? 1 : 0) - (K.is("a", "ArrowLeft") ? 1 : 0);
            const u = typing ? 0 : (K.is(" ") ? 1 : 0) - (K.is("Shift") ? 1 : 0);
            const [dx, dy, dz] = sim.lookDir(this.yaw, this.pitch), yr = this.yaw * DEG, sp = 18 * dt;
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
        if (!show) return;
        this.handT += dt * Math.hypot(s.vx || 0, s.vy || 0);
        const bob = Math.sin(this.handT * 2.2) * 0.02;
        const swing = this.digAt !== null || this.digHit > 0 ? Math.sin(performance.now() / 1000 * 14) * 25 : 0;
        sc.hand.position = new BABYLON.Vector3(0.38, -0.26 + bob, 0.78);
        sc.hand.rotation.x = Math.abs(swing) * DEG;
        const h = sc.hereAt(s.x, s.y, s.z + 1);
        this.handHere[0] = h[0];
        this.handHere[1] = h[1];
    }

    overlay(now) {
        const s = this.meState, w = this.world;
        let under = false;
        if (s && w) {
            const [ex, ey, ez] = sim.eye(s);
            under = w.get(Math.floor(ex), Math.floor(ey), Math.floor(ez)) === sim.B.id.water;
        }
        const debug = this.app.state.showDebug && s ? `x ${s.x.toFixed(1)}  y ${s.y.toFixed(1)}  z ${s.z.toFixed(1)}   looking ${this.yaw.toFixed(0)} ${this.pitch.toFixed(0)}\n` +
            `graphics ${this.scene.tier}   chunks ${this.scene.chunks.size} (${this.scene.todo.size} to draw)\ntime ${this.dayT.toFixed(2)}   things ${this.entities.size}` : "";
        this.hud.update({inv: this.inventory, hp: s ? s.hp : 20, food: s ? s.food : 20, breath: 10, creative: this.creative(),
                         underWater: under, hurt: !!(s && (s.flags & sim.F_HURT)), now, hidden: !this.controlsPlayer(),
                         title: this.titleText(), debug});
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
    onKey(k, e) {
        const S = this.app.state, teacher = S.role !== "learner", now = performance.now();
        if (k === "Escape") {
            if (this.screen) { this.act({type: "close"}); this.closeScreen(false); return true; }
            return false;
        }
        if (k === "e") { this.toggleInventory(); return true; }
        if (this.screen) return ["1", "2", "3", "4", "5", "6", "7", "8", "9", "q", " ", "w"].includes(k);
        if (/^[1-9]$/.test(k)) { this.select(Number(k) - 1); return true; }
        if (k === "q") { this.drop(false); return true; }
        if (k === " ") {  // (in creative, twice quickly flies)
            if (this.creative() && now - this.jumpAt < 300) this.toggleFly();
            this.jumpAt = now;
            return this.controlsPlayer();
        }
        if (k === "w") {  // (twice quickly sprints)
            if (now - this.wAt < 300) this.sprintLock = true;
            this.wAt = now;
            return this.controlsPlayer() || this.view === "free";
        }
        if (k === "f" && this.creative() && this.controlsPlayer()) { this.toggleFly(); return true; }
        if (k === "b") { this.app.openBrainEditor(); return true; }
        if (k === "F3") { S.showDebug = !S.showDebug; return true; }
        if (teacher) {
            const cmd = {t: "time", m: "mobs", g: "gather", k: "kit", n: "mode", F9: "pause"}[k];
            if (cmd) { this.app.send({type: cmd}); return true; }
        }
        if (["a", "s", "d", "Shift", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(k)) return this.controlsPlayer() || this.view === "free";
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
        const rows = [["WASD", "walk (W twice: sprint)"], ["Mouse", "look (click the game first)"], ["Space", "jump (creative: twice to fly)"],
                      ["Shift", "sneak (you won't fall off an edge)"], ["Left button", "dig (held)"], ["Right button", "place, or use the block"],
                      ["1-9, wheel", "the hotbar"], ["Q", "throw one (Ctrl+Q the stack)"], ["E", "inventory and crafting"], ["F", "fly (creative)"],
                      ["V", "view"], ["L", "watch the next learner"], ["B", "your Bot's brain"], ["U", "upload the brain"], ["P", "autopilot"],
                      ["F3", "the numbers"], ["Esc", "close a screen"], ["I or Tab", "the panel"]];
        if (this.app.state.role !== "learner") rows.push(["T", "the time of day"], ["M", "creatures on or off"], ["G", "everyone to you"],
                                                        ["K", "a Bot kit for everyone"], ["N", "creative or survival"], ["F9", "pause"]);
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
        return L ? `Mission ${L.lesson_number} · ${(L.game_mode || "survival").toUpperCase()} · ${L.time === "cycle" ? "day and night" : L.time}${this.paused ? " · PAUSED" : ""}` : "";
    }

    cameraPill() {
        return `Camera: ${VIEW_NAMES[this.view] || this.view}${this.view === "follow" && this.watch !== null ? " " + this.nameOf(this.watch) : ""} (V to change${this.app.state.role !== "learner" ? ", L to watch someone" : ""})`;
    }

    learnerHead() { return ["Player", "Health", "Holding"]; }

    learnerCells(p) {
        const esc = this.app.esc, id = [...this.names.entries()].find(([, n]) => n.kind === "player" && n.name === p.name);
        const e = id ? this.latest.get(id[0]) : null;
        return [e ? `${e.x.toFixed(0)}, ${e.y.toFixed(0)}, ${e.z.toFixed(0)}` : "", e ? `${e.hp} / 20` : "", e && e.held ? esc(sim.nameOf(e.held)) : ""];
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
              <div class="note">EVERYONE TO ME brings the class to where you stand (G); A BOT KIT gives everyone a Bot dock, planks and torches (K); PAUSE stops the world (F9).</div>
              <div class="row"><label>Time of day</label>${TIMES.map(([k, t]) => `<button data-time="${k}" class="${(L.time || "cycle") === k ? "on" : ""}">${t}</button>`).join("")}</div>
              <div class="note">T moves it on (dawn, day, dusk, night, then the cycle again), as the window's.</div>
              <div class="row"><label>The game</label>${on("cr-mode", L.game_mode === "creative", "CREATIVE: fly, every block, nothing hurts", "SURVIVAL")}</div>
              <div class="row"><label>Creatures</label>${on("cr-mobs", !!hz.mobs, "Glitches and Rust Walkers at night", "No creatures")}</div>
              <div class="row"><label>Hunger</label>${on("cr-hunger", hz.hunger !== false && R.hunger !== false, "Food goes down", "Off")}</div>
              <div class="row"><label>Knocked out</label>${on("cr-keep", R.keep_items !== false, "You keep your things", "Your things stay where you fell")}</div>
              <div class="row"><label>Falls</label>${on("cr-falls", R.falls_hurt !== false, "A long fall hurts", "Falls don't hurt")}</div>
              <div class="row"><label>Blast blocks</label>${on("cr-blasts", !!R.blasts, "They go off", "Off")}</div>
              <div class="row"><label>Teacher in the world</label>${on("cr-tplayer", L.teacher_player !== false, "Yes (creative)", "No: watching")}</div>
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
            $("cr-hunger").onclick = () => { const v = !(now().hazards || {}).hunger; lessonSend({hazards: {hunger: v}, rules: {hunger: v}}); };
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
              <div class="note">V changes the view. Flying free: WASD, the mouse, Space up and Shift down.</div>
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
        document.body.classList.remove("craftscreen");
        this.closeScreen(false);
        this.hud.clear();
        this.scene.dispose();
    }
}
