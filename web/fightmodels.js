// Fight Lab's detailed fighters in Club Coders Live (CHANGE 135): the woman, the man and Robin drawn with the app's
// own skinned models (Fight Lab's models/<body>_<shape>.gltf, every Mixamo move in each file) and posed exactly as
// the app's window poses them (fight_model.py, ported below): the same clip for the engine's move (the fighting
// style's or weapon's own first, then the usual one, then a stand-in), the same frame of it for the engine's
// progress (an attack's strike frame lands when the engine's attack is active), whole frames as Panda's
// actor.pose() takes them, the 0.12 s blend from one clip into the next, the cartwheel kick turned over whole in its
// star pose; dressed as fight_model.dress dresses them (the outfit, hair and weapon shown, the rest left out, skin
// under the outfit left out, the outfit's main pieces in the design's colour, the hair in its colour, Robin's trim
// and lights); lit by pbr.js (simplepbr's sums) with each glTF material's own colour, pictures and roughness.
//
// Kept light: a body and shape is fetched once for the page (only when a fighter with it appears), its moves read
// straight from the file's numbers, and loaded once into each scene; each fighter is a copy of it. The primitive
// stand-in (fight.js) is drawn until a fighter's model and pictures are ready, and on the blocks tier. (CHANGE 147) On
// mesh and lines too, as the window's: every piece black, its edges as lines on a copy of its skinned vertices (so they
// bend with every move) and on lines its outline, both bending with it (fight.js's modelLines); on ultra as on high.
//
// Where the models are: ?models=<url> if given, else models/fightlab/ beside the page (the VPS: Caddy serves the
// release's games/fightlab/models there; web_test.py's server does too), else the public repository's or the
// working folder's own folder when the page is served from higher up.
//
// The glTF files are y-up; Babylon's loader turns them into its own axes (its __root__ node), where a model faces
// the game's +y (Panda turns its copy round by 180 degrees for the same). Each joint's numbers are the file's own,
// in the joint's own (glTF) axes: a Panda turn of a joint (h about its z, p about its x, r about its y) is in glTF
// axes a turn about y, x and -z (checked against Panda's controlJoint for the star pose).

/* global BABYLON */

import {v3} from "./base3d.js";
import {toneMap} from "./pbr.js";
import {drawWords} from "./fightfx.js";

export const MODEL_BODIES = ["woman", "man", "robin"];
const HUMAN_BODIES = ["woman", "man"];
const D2R = Math.PI / 180;
const BLEND_TIME = 0.12;  // seconds to blend from one move into the next
// a move a model has no animation for plays another (and in the end, idle)
const FALLBACK = {intro: "idle", dizzy: "hitstun", hit_body: "hitstun", swept: "knockdown", idle_hurt: "idle",
                  launched: "knockdown", cartwheel: "win_power_up"};
// the cartwheel kick's pose: these joints held at the rest pose turned this much (h, p, r; the right side the other way)
const STAR = {UpLeg: [0, 0, -35], Leg: [0, 0, 0], Arm: [-80, 0, 0], ForeArm: [0, 0, 0]};
const TWO_HANDED = ["longsword", "katana", "staff", "glaive"];
const HURT = 0.25;  // below this share of their health, they stand hurt
const WEAPON_PIECES = {knife: ["knife"], dagger: ["dagger"], sword_shield: ["sword", "shield"], longsword: ["longsword"],
                       katana: ["katana"], stick: ["stick"], staff: ["staff"], glaive: ["glaive"]};
// fight_sim.py's rules for a design's look and style (what fight_model.full_look and fight_sim.style_of use)
const STYLES = ["kickboxer", "boxer", "capoeira", "knives", "swords", "sticks"];
const WEAPON_STYLES = ["knives", "swords", "sticks"];  // (the styles with weapons: fight_sim.WEAPONS)
const OUTFITS = ["hoplite", "greek", "commando", "training", "civilian", "warrior"];
const HAIR_STYLES = {woman: ["ponytail", "braid", "long", "bob", "short", "afro"], man: ["short", "classic", "spiky", "crop", "afro", "long"]};
const SHAPES = ["athletic", "muscly", "full"];
const WINS = ["victory", "dance", "bow", "power_up"];
const ROBIN_STYLE = {trim: [140, 145, 155], lights: [255, 90, 25]};

// ---------- the design's look (fight_sim.default_look, check_look; fight_model.full_look) ----------
function defaultLook(body) {
    if (!HUMAN_BODIES.includes(body)) return {shape: "athletic", height: 100, win: "victory"};
    return {outfit: "hoplite", hair: (HAIR_STYLES[body] || ["short"])[0], hair_colour: [70, 40, 25], shape: "athletic", height: 100, win: "victory"};
}

function lookOk(body, look) {
    const whole = v => Number.isInteger(v) && v >= 0 && v <= 255;
    if (HUMAN_BODIES.includes(body)) {
        if (!OUTFITS.includes(look.outfit) || !(HAIR_STYLES[body] || []).includes(look.hair)) return false;
        const c = look.hair_colour;
        if (!(Array.isArray(c) && c.length === 3 && c.every(whole))) return false;
    }
    const h = look.height;
    return SHAPES.includes(look.shape) && typeof h === "number" && h >= 90 && h <= 110 && WINS.includes(look.win ?? "victory");
}

export function fullLook(design) {
    const look = defaultLook(design.body);
    if (design.look && typeof design.look === "object" && !Array.isArray(design.look) && lookOk(design.body, design.look)) Object.assign(look, design.look);
    return look;
}

function styleOf(d) {
    const style = STYLES.includes(d.fighting_style ?? "kickboxer") ? (d.fighting_style ?? "kickboxer") : "kickboxer";
    return [style, WEAPON_STYLES.includes(style) ? (d.weapon ?? null) : null];
}

function animSets(style, weapon) {  // where a fighter's moves come from, first choice first
    const sets = weapon ? [weapon] : [];
    sets.push(style);
    if (TWO_HANDED.includes(weapon)) sets.push("twohand");
    if (["boxer", "kickboxer", "knives"].includes(style)) sets.push("guard");
    return sets;
}

const ease = f => { f = Math.max(0, Math.min(1, f)); return f * f * (3 - 2 * f); };

function cartwheelTurn(k) {  // fight_gfx.cartwheel_turn: how far over (degrees) the cartwheel kick is at progress k
    if (k < 1) return 180 * Math.max(0, k);
    if (k < 2) return 180 + 120 * (k - 1);
    return 300 + 60 * Math.min(1, (k - 2) / 0.4);
}

// ---------- quaternions [x, y, z, w], as glTF and Babylon keep them ----------
function qmul(a, b) {  // a then b in a's frame (Hamilton a*b)
    return [a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
            a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
            a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
            a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2]];
}

function axisTurn(x, y, z, degrees) {
    const s = Math.sin(degrees * D2R / 2);
    return [x * s, y * s, z * s, Math.cos(degrees * D2R / 2)];
}

function pandaTurn(h, p, r) {  // a Panda joint turn (h, p, r) in the joint's glTF axes: r first, then p, then h
    return qmul(qmul(axisTurn(0, 1, 0, h), axisTurn(1, 0, 0, p)), axisTurn(0, 0, -1, r));
}

// ---------- the files ----------
const params = new URLSearchParams(location.search);
const version = () => { const v = (window.__state && window.__state.version) || ""; return v ? `?v=${encodeURIComponent(v)}` : ""; };
let basePromise = null;

function modelBase() {  // {base, moves} for the first place the models are found, or null
    if (!basePromise) basePromise = (async () => {
        const given = params.get("models");
        const tries = given ? [given.endsWith("/") ? given : given + "/"] : ["models/fightlab/", "../games/fightlab/models/", "../../BeatEmUp/models/"];
        for (const base of tries) {
            try {
                const r = await fetch(base + "moves.json", {cache: "no-cache"});
                if (r.ok) return {base, moves: await r.json()};
            } catch (e) { /* not there: the next place */ }
        }
        console.warn("Fight Lab's models weren't found: the fighters are drawn as stand-ins");
        return null;
    })();
    return basePromise;
}

function accessor(json, bin, i) {  // a float accessor's numbers
    const a = json.accessors[i], view = json.bufferViews[a.bufferView];
    const n = {SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4}[a.type] || 1;
    const offset = (view.byteOffset || 0) + (a.byteOffset || 0), stride = view.byteStride || n * 4;
    if (a.componentType !== 5126) throw new Error(`accessor ${i} isn't float`);
    if (stride === n * 4 && offset % 4 === 0) return new Float32Array(bin, offset, a.count * n);
    const out = new Float32Array(a.count * n), dv = new DataView(bin);
    for (let k = 0; k < a.count; k++) for (let c = 0; c < n; c++) out[k * n + c] = dv.getFloat32(offset + k * stride + c * 4, true);
    return out;
}

// one body and shape for the page: the file's numbers (kept, so a scene rebuilt for a new tier loads it again from
// memory), its joints and their rest pose, and its moves, read as Panda reads them (gltf/_converter.py: a clip lasts
// ceil(its last key's time x 30) frames, each frame the keys either side blended)
const files = new Map();

function modelFiles(key) {
    if (!files.has(key)) files.set(key, (async () => {
        const t0 = performance.now();
        const where = await modelBase();
        if (!where) return null;
        const [gr, br] = await Promise.all([fetch(where.base + key + ".gltf" + version()), fetch(where.base + key + ".bin" + version())]);
        if (!gr.ok || !br.ok) return null;
        const json = await gr.json();
        let bin = await br.arrayBuffer();
        if (json.buffers[0].uri !== key + ".bin") {  // (not the usual name)
            const r = await fetch(where.base + json.buffers[0].uri + version());
            if (!r.ok) return null;
            bin = await r.arrayBuffer();
        }
        const fps = where.moves.fps || 30;
        const skin = json.skins[0];
        const slot = new Map(skin.joints.map((node, j) => [node, j]));
        const joints = skin.joints.map(node => {
            const nd = json.nodes[node];
            return {name: nd.name, t: nd.translation || [0, 0, 0], r: nd.rotation || [0, 0, 0, 1], s: nd.scale || [1, 1, 1]};
        });
        const clips = new Map();
        for (const anim of json.animations || []) {
            let last = 0;
            for (const smp of anim.samplers) for (const t of accessor(json, bin, smp.input)) last = Math.max(last, t);
            const channels = [];
            for (const ch of anim.channels) {
                const j = slot.get(ch.target.node), path = {translation: 0, rotation: 1, scale: 2}[ch.target.path];
                if (j === undefined || path === undefined) continue;
                const smp = anim.samplers[ch.sampler];
                channels.push({j, path, times: accessor(json, bin, smp.input), values: accessor(json, bin, smp.output), step: smp.interpolation === "STEP"});
            }
            clips.set(anim.name, {n: Math.max(1, Math.ceil(last * fps)), channels});
        }
        // the loader gets the meshes and the skeleton only (the moves are posed here, the materials made by pbr.js)
        const forLoader = {...json, buffers: [{...json.buffers[0], uri: URL.createObjectURL(new Blob([bin]))}]};
        delete forLoader.animations;
        loadTimes.push([key, "files", Math.round(performance.now() - t0)]);
        return {key, base: where.base, moves: where.moves, fps, json, joints, clips, text: "data:" + JSON.stringify(forLoader)};
    })().catch(e => { console.warn(`Fight Lab model ${key}: ${e}`); return null; }));
    return files.get(key);
}

// the model in a scene: loaded once (an AssetContainer), copied for each fighter
function sceneModel(scene, model) {
    if (!scene.ccModels) {
        scene.ccModels = new Map();
        scene.onDisposeObservable.add(() => { for (const p of scene.ccModels.values()) p.then(c => c && c.dispose()); });
    }
    if (!scene.ccModels.has(model.key)) {
        const t0 = performance.now();
        scene.ccModels.set(model.key, BABYLON.LoadAssetContainerAsync(model.text, scene, {
            pluginExtension: ".gltf",
            pluginOptions: {gltf: {skipMaterials: true, loadNodeAnimations: false, animationStartMode: 0, compileMaterials: false}},
        }).then(c => { loadTimes.push([model.key, "scene", Math.round(performance.now() - t0)]); return c; })
          .catch(e => { console.warn(`Fight Lab model ${model.key} didn't load: ${e}`); return null; }));
    }
    return scene.ccModels.get(model.key);
}

export const loadTimes = [];  // [key, what, ms]: the files fetched and read, a scene's copy loaded, a fighter drawn (the tests)

// (CHANGE 150) A box every pose stays inside: the shown pieces' rest box (their own frame: the model's) grown by 0.6 of
// its biggest side every way (a lying fighter, a kick, a weapon swung over the head), so a body out of the picture or
// out of the shadow's reach is left out (they were drawn always: their bounds are the rest pose's). [min, max]
export function posedBox(meshes) {
    const lo = new BABYLON.Vector3(Infinity, Infinity, Infinity), hi = lo.scale(-1);
    for (const m of meshes) {
        const b = m.getBoundingInfo();
        lo.minimizeInPlace(b.minimum);
        hi.maximizeInPlace(b.maximum);
    }
    const s = hi.subtract(lo), pad = 0.6 * Math.max(s.x, s.y, s.z);
    return [lo.subtractFromFloats(pad, pad, pad), hi.add(new BABYLON.Vector3(pad, pad, pad))];
}

export function withBox(mesh, box) {
    if (!box || !Number.isFinite(box[0].x)) { mesh.alwaysSelectAsActiveMesh = true; return mesh; }
    mesh.alwaysSelectAsActiveMesh = false;
    mesh.setBoundingInfo(new BABYLON.BoundingInfo(box[0], box[1]));
    return mesh;
}

// ---------- a fighter ----------
export class FighterModel {
    // (on the lit tiers, and on mesh and lines since CHANGE 147: black with lines that bend with it, as the window's)
    static wanted(scene, design) {
        return (!!scene.lighting || !!scene.wire) && MODEL_BODIES.includes(design.body);
    }

    // sc: the FightScene, f: fight.js's fighter (its stand-in, pos and h), design: the fighter's design
    constructor(sc, f, design, id) {
        this.sc = sc;
        this.f = f;
        this.design = design;
        this.id = id;
        this.ready = false;
        this.gone = false;
        this.look = fullLook(design);
        this.size = design.model ? 1.3 : ((design.settings || {}).size || 100) / 100;
        [this.style, this.weapon] = styleOf(design);
        this.sets = animSets(this.style, this.weapon);
        this.win = this.look.win || "victory";
        this.clip = this.prev = null;
        this.prevFrame = 0;
        this.clipTime = 0;
        this.fade = 1;
        this.frameNo = 0;
        this.effects = new Map();  // clip -> [control effect, frame posed]: Panda's blending
        this.wheel = null;
        this.star = false;
        this.flashing = false;
        this.t0 = performance.now();
        this.load();
    }

    async load() {
        const body = this.design.body;
        let model = await modelFiles(`${body}_${this.look.shape}`);
        if (!model && this.look.shape !== "athletic") model = await modelFiles(`${body}_athletic`);
        if (!model || this.gone) return;
        const scene = this.sc.scene;
        const container = await sceneModel(scene, model);
        if (!container || this.gone || scene.isDisposed || this.sc.scene !== scene) return;
        try {
            this.build(scene, container, model);
        } catch (e) {  // (the stand-in stays)
            console.warn(`Fight Lab model ${model.key}: ${e}`);
            this.dispose();
        }
    }

    build(scene, container, model) {
        this.model = model;
        this.fps = model.fps;
        this.moves = model.moves.moves || {};
        const made = container.instantiateModelsToScene(name => name, false, {doNotInstantiate: true});
        const root = this.root = new BABYLON.TransformNode("fightermodel" + this.id, scene);
        const body = this.body = new BABYLON.TransformNode("modelbody", scene);  // (turned over whole for the cartwheel kick)
        body.parent = root;
        const scale = new BABYLON.TransformNode("modelscale", scene);
        scale.parent = body;
        scale.scaling.setAll(this.size * 0.975 * this.look.height / 100);  // (the models are 1.80 m; fighters 1.75 m)
        const nodes = new Map();
        for (const r of made.rootNodes) {
            r.parent = scale;
            for (const x of [r, ...r.getDescendants(false)]) if (!nodes.has(x.name)) nodes.set(x.name, x);
        }
        this.joints = model.joints.map(j => {
            const node = nodes.get(j.name);
            if (node && !node.rotationQuaternion) node.rotationQuaternion = BABYLON.Quaternion.FromArray(j.r);
            return node || null;
        });
        this.starJoints = [];  // [joint, its held rotation]
        for (const [side, sign] of [["Left", 1], ["Right", -1]]) for (const [part, [h, p, r]] of Object.entries(STAR)) {
            const j = model.joints.findIndex(x => x.name === `mixamorig:${side}${part}`);
            if (j >= 0) this.starJoints.push([j, qmul(model.joints[j].r, pandaTurn(h * sign, p * sign, r * sign))]);
        }
        this.meshes = this.dress(made.rootNodes.flatMap(r => r.getChildMeshes(false)), model.json);
        root.setEnabled(false);  // (until every part's shader and pictures are ready: the stand-in is drawn till then)
        this.sc.shadowCast(this.meshes);
        if (this.design.body === "robin") this.numberPlate(nodes.get("mixamorig:Spine2"), scale);
    }

    // fight_model.number_plate: Robin's number (or name) on the chest plate's face under the core light, in the light
    // colour and unlit. The window's place in the Spine2 joint's Panda axes, (0, -0.236, 0.012) leaning back 19.3
    // degrees, is (0, 0.012, 0.236) in its glTF axes (Panda x, y, z = glTF x, -z, y); the plate's centre is the text's
    // middle, 0.016 up the plate from the baseline. The joint's own units are scaled back to the model's metres.
    numberPlate(joint, scale) {
        const style = this.design.style || {};
        const text = String(style.number || this.design.name || "").slice(0, 8);
        if (!joint || !text) return;
        const scene = this.sc.scene;
        const plane = BABYLON.MeshBuilder.CreatePlane("robinnumber", {width: 0.24, height: 0.06}, scene);
        const tex = new BABYLON.DynamicTexture("robinnumbertex", {width: 256, height: 64}, scene, true);
        tex.hasAlpha = true;
        tex.getContext().clearRect(0, 0, 256, 64);
        // (unlit, but the app's tone pass still curves it, so a paler colour than the light colour itself; on the line
        // tiers white, shown in the line colour: CHANGE 147)
        const colour = this.sc.wire ? [1, 1, 1] : toneMap((style.lights || ROBIN_STYLE.lights).map(c => c / 255), this.sc.lighting ? this.sc.lighting.exposure : 1);
        // (CHANGE 150: in the window's letters, 0.045 m a unit: 48 pixels a unit on this 0.24 m picture, the baseline
        // 0.016 m below its middle; the browser's sans if they haven't come)
        const css = `rgb(${colour.map(c => Math.round(255 * Math.min(1, c))).join(",")})`;
        if (!drawWords(tex.getContext(), text, 128, 49, 48, css)) tex.drawText(text, null, 49, "48px sans-serif", css, null, true, true);
        else tex.update();
        const m = new BABYLON.StandardMaterial("robinnumbermat", scene);
        m.diffuseTexture = tex;
        m.emissiveColor = new BABYLON.Color3(1, 1, 1);
        m.disableLighting = true;
        m.backFaceCulling = false;
        m.useAlphaFromDiffuseTexture = true;
        plane.material = m;
        plane.isPickable = false;
        scale.computeWorldMatrix(true);
        joint.computeWorldMatrix(true);
        const k = scale.absoluteScaling.x / joint.absoluteScaling.x;  // (model metres in the joint's units)
        plane.parent = joint;
        plane.position.set(0, 0.0271 * k, 0.2307 * k);
        plane.rotation.set(-19.3 * D2R, 0, 0);  // (the loader mirrors x: the plane reads from its back, here the front)
        plane.scaling.setAll(k);
        if (this.sc.wire) this.sc.lettering(plane);
        this.plate = plane;
    }

    // fight_model.dress: show the chosen outfit, hairstyle and weapon (the rest are thrown away), colour the clothes
    // and the hair (or Robin's plating, trim and lights); each piece gets its glTF material lit by pbr.js
    dress(meshes, json) {
        const look = this.look, style = this.design.style || {};
        const weapons = WEAPON_PIECES[this.weapon] || [];
        // the tint multiplies the lighting's linear colours: screen colour -> linear, divided by the grey the main
        // pieces (0.85 on screen) and the hair (about 0.8) already are
        const lin = c => Math.pow(c / 255, 2.2);
        const main = (this.design.colour || [200, 200, 200]).map(c => Math.min(2.0, lin(c) / 0.7));
        const hair = (look.hair_colour || [70, 40, 25]).map(c => Math.min(2.5, 0.02 + lin(c) / 0.6));
        const trim = (style.trim || ROBIN_STYLE.trim).map(c => Math.min(2.0, lin(c) / 0.7));
        const lights = (style.lights || ROBIN_STYLE.lights).map(c => lin(c) * 2.5);
        const order = this.model.moves.outfits || [];
        const bit = order.includes(look.outfit) ? 1 << order.indexOf(look.outfit) : 0;
        const nodeByName = new Map(json.nodes.filter(n => n.mesh !== undefined).map(n => [n.name, n]));
        const images = (json.images || []).map(im => im.uri ? this.model.base + im.uri.split("/").map(encodeURIComponent).join("/") + version() : null);
        const picture = info => info && json.textures[info.index] ? images[json.textures[info.index].source] : null;
        this.mats = new Map();  // "<material>:<tint>" -> [material, its glTF base colour, its tint]
        const groups = new Map();  // "<material>:<tint>" -> the pieces drawn with it
        const wire = !!this.sc.wire;  // (mesh and lines: every piece black, its lines made below: CHANGE 147)
        for (const mesh of meshes) {
            const m = /^(.*)_primitive(\d+)$/.exec(mesh.name);
            const name = m && !nodeByName.has(mesh.name) ? m[1] : mesh.name, prim = m && !nodeByName.has(mesh.name) ? Number(m[2]) : 0;
            const node = nodeByName.get(name);
            let show;
            if (name.startsWith("skin.")) show = /^\d+$/.test(name.slice(5)) ? !(Number(name.slice(5)) & bit) : true;  // (skin under the outfit: left out, so it can't poke through)
            else if (name.startsWith("outfit_")) show = name.startsWith(`outfit_${look.outfit}.`);
            else if (name.startsWith("hair.")) show = name === `hair.${look.hair}`;
            else if (name.startsWith("weapon.")) show = weapons.includes(name.slice(7));
            else show = true;
            const primitive = node ? json.meshes[node.mesh].primitives[prim] : null;
            if (!show || !primitive) { mesh.dispose(false, false); continue; }
            const kind = name.includes(".main_") ? "main" : name.includes(".trim_") ? "trim" : name.includes(".light_") ? "light"
                       : name.startsWith("hair.") ? "hair" : "";
            const tint = {main, trim, hair}[kind] || [1, 1, 1];
            const index = primitive.material ?? -1, key = wire ? "wire" : `${index}:${kind}`;
            if (!wire && !this.mats.has(key)) {
                const g = json.materials[index] || {}, pbr = g.pbrMetallicRoughness || {};
                const factor = pbr.baseColorFactor || [1, 1, 1, 1];
                const mat = this.sc.lighting.material(`fightermodel${this.id}:${g.name || index}:${kind}`, {
                    linear: [factor[0] * tint[0], factor[1] * tint[1], factor[2] * tint[2], factor[3]],
                    rough: pbr.roughnessFactor ?? 1, metal: pbr.metallicFactor ?? 1,
                    emission: kind === "light" ? lights : (g.emissiveFactor || [0, 0, 0]),  // (Robin's lights glow in the light colour)
                    albedoUrl: picture(pbr.baseColorTexture), mrUrl: picture(pbr.metallicRoughnessTexture),
                    blend: g.alphaMode === "BLEND",
                });
                mat.forceDepthWrite = true;  // (panda3d-gltf's alpha blending still writes depth: the skin is blended too)
                this.mats.set(key, [mat, factor, tint]);
            }
            const group = `${key}|${mesh.skeleton ? "posed" : "still"}`;  // (Robin has one stray piece without a skin)
            if (!groups.has(group)) groups.set(group, [key, []]);
            groups.get(group)[1].push(mesh);
        }
        const kept = [];
        for (const [key, list] of groups.values()) {
            const mesh = list.length > 1 ? this.merged(list) : list[0];
            mesh.material = wire ? this.sc.wireFill() : this.mats.get(key)[0];
            mesh.isPickable = false;
            kept.push(mesh);
        }
        this.box = posedBox(kept);
        for (const mesh of kept) withBox(mesh, this.box);
        this.lines = wire ? this.sc.modelLines(kept, this.box) : null;  // ([[mesh, its material, its hit flash's]])
        return kept;
    }

    // the pieces that share a material as one mesh (Robin is 125 pieces): made once per scene for these pieces, a copy
    // (sharing it) for each fighter dressed the same, on this fighter's skeleton. The pieces are siblings with the same
    // place, so their vertices are merged as they are.
    merged(list) {
        const scene = this.sc.scene, first = list[0];
        if (!scene.ccMerged) scene.ccMerged = new Map();
        const key = `${this.model.key}|${list.map(m => m.name).sort().join(",")}`;
        let made = scene.ccMerged.get(key);
        if (!made) {
            const data = list.map(m => BABYLON.VertexData.ExtractFromMesh(m, true, true));
            const all = data[0];
            all.merge(data.slice(1), true);
            made = new BABYLON.Mesh("fightermerged", scene);
            all.applyToMesh(made, false);
            made.geometry.ccPieces = data.map(d => d.positions.length / 3);  // (the line tiers find each piece's edges apart: CHANGE 150)
            made.setEnabled(false);  // (never drawn itself)
            made.isPickable = false;
            scene.ccMerged.set(key, made);
        }
        const mesh = made.clone("fighterpart", first.parent, true);
        mesh.setEnabled(true);
        mesh.position.copyFrom(first.position);
        mesh.rotationQuaternion = first.rotationQuaternion ? first.rotationQuaternion.clone() : null;
        if (!first.rotationQuaternion) mesh.rotation.copyFrom(first.rotation);
        mesh.scaling.copyFrom(first.scaling);
        mesh.skeleton = first.skeleton;
        mesh.numBoneInfluencers = first.numBoneInfluencers;
        for (const m of list) m.dispose(false, false);
        return mesh;
    }

    // ---------- which frame of which animation (fight_model.clip_for and frame_for) ----------
    clipFor(a) {
        const seen = new Set();
        while (a && !seen.has(a)) {
            seen.add(a);
            for (const name of [...this.sets.map(s => `${s}.${a}`), a]) if (this.model.clips.has(name) && this.moves[name]) return name;
            a = FALLBACK[a] || "idle";
        }
        return "idle";
    }

    frameFor(a, k) {
        const n = this.model.clips.get(a).n, m = this.moves[a], play = m.play;
        if (play === "loop") return (this.clipTime * this.fps) % n;
        if (play === "once") return Math.min(n - 1, Math.max(0, k) * (n - 1));
        if (play === "reverse") return (1 - Math.min(1, Math.max(0, k))) * (n - 1);
        if (play === "hold") return Math.min(n - 1, this.clipTime * this.fps);
        // an attack: wind-up (k 0-1) up to the strike frame, the strike itself (1-2), then the recovery (2-3)
        const peak = Math.min(n - 2, Math.max(1, m.peak));
        const strike = Math.max(1, 0.12 * (n - peak));
        let f;
        if (k < 1) f = k * peak;
        else if (k < 2) f = peak + (k - 1) * strike;
        else f = peak + strike + Math.min(1, k - 2) * (n - 1 - peak - strike);
        return Math.max(0, Math.min(n - 1, f));
    }

    show(on) {
        if (this.ready) this.root.setEnabled(on);
    }

    // each frame the fighter is on the stage, from fight.js: s is this fighter's state (pos, h, a, k, hp, max, hu...),
    // f.pos and f.h already smoothed as the app smooths them
    frame(s, dt) {
        if (!this.root || !this.meshes || this.gone) return;
        if (!this.ready) {
            if (!this.meshes.every(m => m.isReady(true))) return;
            this.ready = true;
            loadTimes.push([this.model.key, "drawn", Math.round(performance.now() - this.t0)]);  // (from the fighter appearing)
            this.f.body.setEnabled(false);  // (the stand-in goes)
            this.f.labelLift = 0.2;  // (the window's name tag over a model)
        }
        this.root.setEnabled(true);
        const f = this.f;
        this.root.position = v3(f.pos[0], f.pos[1], f.pos[2]);
        this.root.rotation.y = -f.h * D2R;
        let a = s.a || "idle";
        const k = s.k || 0;
        if (a === "win") a = `win_${this.win}`;
        else if (a === "idle" && (s.hp ?? 1) < HURT * (s.max ?? 1)) a = "idle_hurt";
        const name = this.clipFor(a);
        if (name !== this.clip) {  // a new move: blend from the old one over a moment
            this.prev = this.clip;
            this.prevFrame = this.frameNo;
            this.clip = name;
            this.clipTime = 0;
            this.fade = 0;
        } else this.clipTime += dt;
        this.fade = Math.min(1, this.fade + dt / BLEND_TIME);
        const frame = this.frameFor(name, k);
        this.frameNo = frame;
        this.effects.set(name, [this.fade, Math.floor(frame)]);  // (Panda's actor.pose takes whole frames)
        if (this.prev && this.prev !== name) {
            if (this.fade < 1) this.effects.set(this.prev, [1 - this.fade, Math.floor(this.prevFrame)]);
            else { this.effects.set(this.prev, [0, Math.floor(this.prevFrame)]); this.prev = null; }
        }
        // (user mod) the cartwheel kick, as the window does it: the body turns side-on and goes right over about its
        // middle, in the star pose (the models have no cartwheel of their own)
        if (s.a === "cartwheel") {
            const over = cartwheelTurn(k);
            this.wheel = this.wheel === null || over < this.wheel - 1 ? over : Math.min(over, this.wheel + 900 * dt);
            this.star = true;
            const h = 90 * Math.min(ease(k * 4), ease((3 - k) * 2.5));
            this.body.rotation.set(0, -h * D2R, -this.wheel * D2R);
            const mid = new BABYLON.Vector3(0, 0.9 * this.size, 0);
            const rise = 1 + 0.22 * Math.sin(this.wheel / 2 * D2R) ** 2;  // (higher on the hands: the arms are up)
            const turned = mid.rotateByQuaternionToRef(BABYLON.Quaternion.RotationYawPitchRoll(-h * D2R, 0, -this.wheel * D2R), new BABYLON.Vector3());
            this.body.position = mid.scale(rise).subtract(turned);
        } else if (this.wheel !== null) {
            this.wheel = null;
            this.star = false;
            this.body.position.setAll(0);
            this.body.rotation.setAll(0);
        }
        this.pose();
        const hurt = (s.hu ?? 9) < 0.12;  // a hit flash: bright for a moment
        if (hurt !== this.flashing) {
            this.flashing = hurt;
            for (const [m, base, white] of this.lines || []) m.material = hurt ? white : base;  // (the line tiers: CHANGE 147)
            const scale = hurt ? [2.6, 2.3, 2.1] : [1, 1, 1];
            for (const [mat, factor, tint] of this.mats.values()) {
                mat.setColor4("baseColor", new BABYLON.Color4(factor[0] * tint[0] * scale[0], factor[1] * tint[1] * scale[1], factor[2] * tint[2] * scale[2], factor[3]));
            }
        }
    }

    // every joint from the clips in play, each by its control effect (Panda's normalised blending: a clip keeps the
    // frame and the effect it was last given), the star pose's joints held
    pose() {
        const J = this.model.joints, n = J.length, fps = this.fps;
        const acc = this.acc || (this.acc = new Float64Array(n * 10)), got = this.got || (this.got = new Uint8Array(n * 3));
        acc.fill(0);
        let total = 0;
        const v = [0, 0, 0, 0];
        for (const [name, [w, frame]] of this.effects) {
            if (w <= 0) continue;
            total += w;
            const clip = this.model.clips.get(name), t = frame / fps;
            got.fill(0);
            for (const ch of clip.channels) {
                sample(ch, t, v);
                const o = ch.j * 10, slot = ch.j * 3 + ch.path;
                if (got[slot]) continue;
                got[slot] = 1;
                if (ch.path === 0) { acc[o] += v[0] * w; acc[o + 1] += v[1] * w; acc[o + 2] += v[2] * w; }
                else if (ch.path === 2) { acc[o + 7] += v[0] * w; acc[o + 8] += v[1] * w; acc[o + 9] += v[2] * w; }
                else {
                    const flip = acc[o + 3] * v[0] + acc[o + 4] * v[1] + acc[o + 5] * v[2] + acc[o + 6] * v[3] < 0 ? -w : w;
                    acc[o + 3] += v[0] * flip; acc[o + 4] += v[1] * flip; acc[o + 5] += v[2] * flip; acc[o + 6] += v[3] * flip;
                }
            }
            for (let j = 0; j < n; j++) {  // (a joint this clip doesn't move: its rest pose)
                const o = j * 10, rest = J[j];
                if (!got[j * 3]) for (let c = 0; c < 3; c++) acc[o + c] += rest.t[c] * w;
                if (!got[j * 3 + 1]) {
                    const flip = acc[o + 3] * rest.r[0] + acc[o + 4] * rest.r[1] + acc[o + 5] * rest.r[2] + acc[o + 6] * rest.r[3] < 0 ? -w : w;
                    for (let c = 0; c < 4; c++) acc[o + 3 + c] += rest.r[c] * flip;
                }
                if (!got[j * 3 + 2]) for (let c = 0; c < 3; c++) acc[o + 7 + c] += rest.s[c] * w;
            }
        }
        for (let j = 0; j < n; j++) {
            const node = this.joints[j];
            if (!node) continue;
            const o = j * 10, rest = J[j];
            if (total <= 0) {  // (nothing in play yet: the rest pose)
                node.position.set(rest.t[0], rest.t[1], rest.t[2]);
                node.rotationQuaternion.set(rest.r[0], rest.r[1], rest.r[2], rest.r[3]);
                node.scaling.set(rest.s[0], rest.s[1], rest.s[2]);
                continue;
            }
            node.position.set(acc[o] / total, acc[o + 1] / total, acc[o + 2] / total);
            const len = Math.hypot(acc[o + 3], acc[o + 4], acc[o + 5], acc[o + 6]) || 1;
            node.rotationQuaternion.set(acc[o + 3] / len, acc[o + 4] / len, acc[o + 5] / len, acc[o + 6] / len);
            node.scaling.set(acc[o + 7] / total, acc[o + 8] / total, acc[o + 9] / total);
        }
        if (this.star) for (const [j, q] of this.starJoints) {  // (Panda's controlJoint: held at the rest pose turned)
            const node = this.joints[j], rest = J[j];
            if (!node) continue;
            node.position.set(rest.t[0], rest.t[1], rest.t[2]);
            node.rotationQuaternion.set(q[0], q[1], q[2], q[3]);
            node.scaling.set(rest.s[0], rest.s[1], rest.s[2]);
        }
    }

    dispose() {
        this.gone = true;
        if (this.plate) { this.plate.dispose(false, true); this.plate = null; }  // (its own picture and material)
        if (this.root) this.root.dispose(false, false);  // (the pictures are shared: kept)
        for (const [mat] of (this.mats || new Map()).values()) mat.dispose(false, false);
        this.root = null;
    }
}

// a channel's value at time t (gltf/_converter.py: the keys either side, rotations slerped the short way)
function sample(ch, t, out) {
    const T = ch.times, V = ch.values, n = T.length, w = ch.path === 1 ? 4 : 3;
    let i;
    if (n === 1 || t <= T[0]) i = 0;
    else if (t >= T[n - 1]) i = n - 1;
    else {
        let lo = 0, hi = n - 1;  // T[lo] <= t < T[hi]
        while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (T[mid] <= t) lo = mid; else hi = mid; }
        const f = ch.step ? 0 : (t - T[lo]) / (T[hi] - T[lo]);
        if (f <= 0) i = lo;
        else {
            const a = lo * w, b = hi * w;
            if (w === 3) { for (let c = 0; c < 3; c++) out[c] = V[a + c] + (V[b + c] - V[a + c]) * f; return; }
            let dot = V[a] * V[b] + V[a + 1] * V[b + 1] + V[a + 2] * V[b + 2] + V[a + 3] * V[b + 3];
            const sa = dot < 0 ? -1 : 1;
            dot = Math.abs(dot);
            let ka, kb;
            if (dot > 0.9995) { ka = 1 - f; kb = f; }
            else { const th = Math.acos(dot), s = Math.sin(th); ka = Math.sin((1 - f) * th) / s; kb = Math.sin(f * th) / s; }
            let len = 0;
            for (let c = 0; c < 4; c++) { out[c] = V[a + c] * sa * ka + V[b + c] * kb; len += out[c] * out[c]; }
            len = Math.sqrt(len) || 1;
            for (let c = 0; c < 4; c++) out[c] /= len;
            return;
        }
    }
    for (let c = 0; c < w; c++) out[c] = V[i * w + c];
}

window.__fightModels = {loadTimes};  // (the tests: how long the models took)
