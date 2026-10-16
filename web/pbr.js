// The app's lighting in the browser (CHANGE 131): simplepbr's shader (panda3d-simplepbr 0.13, the one every game's
// window draws with) ported to a Babylon ShaderMaterial, so the page's low, medium and high tiers light a scene with
// the same sums as the app's: the GGX highlights, the Lambert diffuse, the ambient term, the reflections (the nine
// spherical-harmonic numbers and the blurred sky that make_textures.py works out with simplepbr's own functions),
// the shadow from the key light, and the tone curve (exposure, then the Hejl-Burgess filmic curve) at each game's
// exposure. The tone curve is applied as each pixel is drawn rather than in a pass afterwards: the same numbers, no
// extra full-screen pass, and the canvas's own multisampling smooths the edges.
//
// Babylon's world is the game's with y and z swapped (base3d.js); the sky's numbers and pictures are in game
// coordinates, so a normal or a reflection is swapped back before it looks them up.

/* global BABYLON */

const VERT = `
precision highp float;
attribute vec3 position;
attribute vec3 normal;
attribute vec2 uv;
#ifdef VERTEXCOLOR
attribute vec4 color;
#endif
#include<instancesDeclaration>
#include<bonesDeclaration>
uniform mat4 viewProjection;
varying vec3 vPos;
varying vec3 vNormal;
varying vec2 vUV;
#if defined(VERTEXCOLOR) || defined(INSTANCESCOLOR)
varying vec4 vColor;
#endif
void main(void) {
#include<instancesVertex>
#include<bonesVertex>
    vec4 wp = finalWorld * vec4(position, 1.0);
    vPos = wp.xyz;
    vNormal = mat3(finalWorld) * normal;
    vUV = uv;
#if defined(VERTEXCOLOR) || defined(INSTANCESCOLOR)
    vColor = vec4(1.0);
#endif
#ifdef VERTEXCOLOR
    vColor = color;
#endif
#ifdef INSTANCESCOLOR
    vColor *= instanceColor;  // (a thin instance's own colour, linear: Kart Lab's ultra circuit, CHANGE 144)
#endif
    gl_Position = viewProjection * wp;
}`;

const FRAG = `
precision highp float;
#ifndef NUM_LIGHTS
#define NUM_LIGHTS 1
#endif
uniform vec4 baseColor;
uniform vec3 emission;
uniform float roughness;
uniform float metallic;
uniform vec3 camPos;
uniform vec3 ambient;
uniform float exposure;
uniform float visibility;
uniform vec3 fill;                   // the sky's light, its reflections, the ambient beside them: x 1 unless a game says
uniform vec4 lightPos[NUM_LIGHTS];   // xyz: the position, or the direction to the light when w is 0
uniform vec3 lightCol[NUM_LIGHTS];
uniform vec3 lightAtt[NUM_LIGHTS];   // constant, linear, quadratic
uniform vec4 lightSpot[NUM_LIGHTS];  // xyz: a spotlight's direction, w: the cosine of its cut-off (-1: not a spot)
#if defined(TEXTURED) || defined(ALBEDOMAP)
uniform sampler2D albedoTex;
#endif
#if defined(TEXTURED) || defined(MRMAP)
uniform sampler2D mrTex;
#endif
#ifdef NORMALMAP
uniform sampler2D normalTex;
#endif
#ifdef GLOWMAP
uniform sampler2D glowTex;           // (CHANGE 145: each part's glow from a picture, times emission)
#endif
#ifdef IBL
uniform vec3 sh[9];
uniform sampler2D reflectTex;
uniform sampler2D brdfTex;
#endif
#ifdef SHADOWS
uniform highp sampler2DShadow shadowMap;
uniform mat4 shadowMatrix;
uniform float shadowBias;
#endif
#ifdef PROBE
uniform samplerCube probeTex;
#endif
#ifdef CLEARCOAT
uniform float clearcoat;
#endif
#ifdef FOG
uniform vec3 fogColor;
uniform float fogDensity;
#endif
varying vec3 vPos;
varying vec3 vNormal;
varying vec2 vUV;
#if defined(VERTEXCOLOR) || defined(INSTANCESCOLOR)
varying vec4 vColor;
#endif
const float PI = 3.141592653589793;
const vec3 F0 = vec3(0.04);

#ifdef NORMALMAP
mat3 cotangentFrame(vec3 n, vec3 p, vec2 uv) {
    vec3 dp1 = dFdx(p), dp2 = dFdy(p);
    vec2 duv1 = dFdx(uv), duv2 = dFdy(uv);
    vec3 dp2perp = cross(dp2, n), dp1perp = cross(n, dp1);
    vec3 t = dp2perp * duv1.x + dp1perp * duv2.x;
    vec3 b = dp2perp * duv1.y + dp1perp * duv2.y;
    float invmax = inversesqrt(max(max(dot(t, t), dot(b, b)), 1e-12));
    return mat3(t * invmax, b * invmax, n);
}
#endif

#ifdef IBL
vec3 irradianceFromSh(vec3 n) {  // (simplepbr's irradiance_from_sh, in game coordinates)
    return sh[0] * 0.282095
        + sh[1] * 0.488603 * n.x
        + sh[2] * 0.488603 * n.z
        + sh[3] * 0.488603 * n.y
        + sh[4] * 1.092548 * n.x * n.z
        + sh[5] * 1.092548 * n.y * n.z
        + sh[6] * 1.092548 * n.y * n.x
        + sh[7] * (0.946176 * n.z * n.z - 0.315392)
        + sh[8] * 0.546274 * (n.x * n.x - n.y * n.y);
}

// the blurred sky: four levels (rough 0, 1/3, 2/3, 1) one above the other, each a latitude-longitude picture whose
// top row looks straight up (game z); lod as simplepbr's textureCubeLod (roughness x 4, the last level from 0.75)
vec3 envLookup(vec3 d, float lod) {
    float u = atan(d.y, d.x) / (2.0 * PI) + 0.5;
    float v = acos(clamp(d.z, -1.0, 1.0)) / PI;
    v = clamp(v, 0.02, 0.98);
    lod = clamp(lod, 0.0, 3.0);
    float l0 = floor(lod), l1 = min(l0 + 1.0, 3.0);
    vec3 a = texture2D(reflectTex, vec2(u, (l0 + v) / 4.0)).rgb;
    vec3 b = texture2D(reflectTex, vec2(u, (l1 + v) / 4.0)).rgb;
#ifdef ENVSRGB
    return pow(mix(a, b, lod - l0), vec3(2.2));  // (the sky picture's colours are a screen's: their light is linear)
#else
    return mix(a, b, lod - l0);
#endif
}

// the reflection along r (Babylon's axes): the blurred sky, and on ultra (PROBE) the world round the kart watched,
// as a cube drawn every few frames, for the smoother surfaces (CHANGE 144)
vec3 reflection(vec3 r, float rough) {
    vec3 env = envLookup(vec3(r.x, r.z, r.y), rough * 4.0);
#ifdef PROBE
    vec3 pr = textureLod(probeTex, r, rough * 7.0).rgb;
    pr = pow(pr, vec3(2.2)) / max(exposure, 0.1);  // (drawn through the tone curve: near enough back out of it)
    env = mix(pr, env, smoothstep(0.3, 0.75, rough));
#endif
    return env;
}
#endif

#ifdef SHADOWS
float shadowAt(vec3 p) {
    vec4 s = shadowMatrix * vec4(p, 1.0);
    vec3 c = s.xyz / s.w;
    vec2 uv = c.xy * 0.5 + 0.5;
    if (uv.x <= 0.0 || uv.x >= 1.0 || uv.y <= 0.0 || uv.y >= 1.0 || c.z >= 1.0) return 1.0;
#ifdef SOFTSHADOW
    // (ultra, CHANGE 144) twelve taps round the point, each the hardware's own 2 x 2 comparison: a soft edge
    vec2 texel = 1.6 / vec2(textureSize(shadowMap, 0));
    float z = c.z * 0.5 + 0.5 - shadowBias, sum = 0.0;
    const vec2 taps[12] = vec2[12](vec2(-0.326, -0.406), vec2(-0.840, -0.074), vec2(-0.696, 0.457), vec2(-0.203, 0.621),
        vec2(0.962, -0.195), vec2(0.473, -0.480), vec2(0.519, 0.767), vec2(0.185, -0.893), vec2(0.507, 0.064),
        vec2(0.896, 0.412), vec2(-0.322, -0.933), vec2(-0.792, -0.598));
    for (int i = 0; i < 12; i++) sum += texture(shadowMap, vec3(uv + taps[i] * texel, z));
    return sum / 12.0;
#else
    return texture(shadowMap, vec3(uv, c.z * 0.5 + 0.5 - shadowBias));
#endif
}
#endif

void main(void) {
    vec4 mr = vec4(1.0);
    vec4 albedo = vec4(1.0);
#if defined(TEXTURED) || defined(MRMAP)
    mr = texture2D(mrTex, vUV);
#endif
#if defined(TEXTURED) || defined(ALBEDOMAP)
    albedo = texture2D(albedoTex, vUV);
    albedo.rgb = pow(albedo.rgb, vec3(2.2));  // (an sRGB picture, as the app loads it)
#endif
    float metal = clamp(metallic * mr.b, 0.0, 1.0);
    float prough = clamp(roughness * mr.g, 0.0, 1.0);
    float arough = prough * prough;
    vec4 base = baseColor * albedo;
#if defined(VERTEXCOLOR) || defined(INSTANCESCOLOR)
    base *= vColor;  // (the app's vertex colours are linear: simplepbr multiplies them in as they are)
#endif
    vec3 diffuseColor = base.rgb * (vec3(1.0) - F0) * (1.0 - metal);
    vec3 specColor = mix(F0, base.rgb, metal);
    vec3 v = normalize(camPos - vPos);
    vec3 n = normalize(vNormal);
    vec3 ng = normalize(cross(dFdx(vPos), dFdy(vPos)));  // (both sides are drawn: the face turned to the camera)
    if (dot(ng, v) < 0.0) ng = -ng;
    if (dot(n, ng) < 0.0) n = -n;
#ifdef NORMALMAP
    vec2 nxy = 2.0 * texture2D(normalTex, vUV).rg - 1.0;
    vec3 nm = vec3(nxy, sqrt(clamp(1.0 - dot(nxy, nxy), 0.0, 1.0)));
    n = normalize(cotangentFrame(n, vPos, vUV) * nm);
#endif
    float ao = 1.0;
#ifdef OCCLUSION
    ao = mr.r;
#endif
    float ndotv = clamp(abs(dot(n, v)), 0.0, 1.0);
    vec3 color = vec3(0.0);
#ifdef CLEARCOAT
    vec3 nc = normalize(vNormal);  // (the coat is smooth over the paint's bumps)
    if (dot(nc, ng) < 0.0) nc = -nc;
    vec3 coat = vec3(0.0);
#endif
    for (int i = 0; i < NUM_LIGHTS; ++i) {
        vec3 lc = lightCol[i];
        if (dot(lc, lc) < 0.001) continue;
        vec3 lp = lightPos[i].xyz - vPos * lightPos[i].w;
        vec3 l = normalize(lp);
        vec3 h = normalize(l + v);
        float dist = length(lp);
        vec3 att = lightAtt[i];
        float attenuation = 1.0 / (att.x + att.y * dist + att.z * dist * dist);
        float cutoff = lightSpot[i].w;
        float spot = cutoff > 0.001 ? smoothstep(cutoff - 0.001, cutoff + 0.001, dot(lightSpot[i].xyz, -l)) : 1.0;
        float caster = 1.0;
#ifdef SHADOWS
        if (i == 0) caster = shadowAt(vPos);
#endif
        float ndotl = clamp(dot(n, l), 0.0, 1.0);
        float ndoth = clamp(dot(n, h), 0.0, 1.0);
        float vdoth = clamp(dot(v, h), 0.0, 1.0);
        vec3 F = specColor + (vec3(1.0) - specColor) * pow(2.0, (-5.55473 * vdoth - 6.98316) * vdoth);
        float r2 = arough * arough;
        float ggx = ndotl * sqrt(ndotv * ndotv * (1.0 - r2) + r2) + ndotv * sqrt(ndotl * ndotl * (1.0 - r2) + r2);
        float vis = ggx > 0.0 ? 0.5 / ggx : 0.0;
        float f = ndoth * ndoth * (r2 - 1.0) + 1.0;
        float D = r2 / (PI * f * f);
        color += ndotl * lc * (diffuseColor / PI + F * vis * D) * spot * caster * attenuation;
#ifdef CLEARCOAT
        float cl = clamp(dot(nc, l), 0.0, 1.0), ch = clamp(dot(nc, h), 0.0, 1.0), cvv = clamp(dot(nc, v), 0.0, 1.0);
        const float cr2 = 0.0016;  // (the coat's roughness 0.2, squared twice as above)
        float cg = cl * sqrt(cvv * cvv * (1.0 - cr2) + cr2) + cvv * sqrt(cl * cl * (1.0 - cr2) + cr2);
        float cf = ch * ch * (cr2 - 1.0) + 1.0;
        coat += cl * lc * (0.04 + 0.96 * pow(1.0 - vdoth, 5.0)) * clearcoat * (cg > 0.0 ? 0.5 / cg : 0.0)
              * cr2 / (PI * cf * cf) * spot * caster * attenuation;
#endif
    }
#ifdef IBL
    vec3 gn = vec3(n.x, n.z, n.y);
    vec3 iblF = specColor + (max(vec3(1.0 - prough), specColor) - specColor) * pow(clamp(1.0 - ndotv, 0.0, 1.0), 5.0);
    vec3 kd = (1.0 - iblF) * (1.0 - metal);
    vec3 iblDiff = base.rgb * max(irradianceFromSh(gn), 0.0) / PI;
    vec3 r = reflect(-v, n);
    vec2 envBrdf = texture2D(brdfTex, vec2(ndotv, prough)).rg;
    vec3 iblSpec = reflection(r, prough) * (iblF * envBrdf.x + envBrdf.y);
    color += (kd * iblDiff * fill.x + iblSpec * fill.y) * ao;
    color += (diffuseColor + specColor) * ambient * ao * fill.z;
#else
    color += (diffuseColor + specColor) * ambient * ao;
#endif
#if defined(CLEARCOAT) && defined(IBL)
    // (ultra, CHANGE 144) a clear coat over the paint: its own sharp highlight from each light and its own
    // reflection of the world, with the light it reflects taken from the layer under it
    float cv = clamp(dot(nc, v), 0.0, 1.0);
    float cF = (0.04 + 0.96 * pow(1.0 - cv, 5.0)) * clearcoat;
    color = color * (1.0 - cF) + coat + reflection(reflect(-v, nc), 0.0) * cF * fill.y;
#endif
#ifdef GLOWMAP
    color += emission * texture2D(glowTex, vUV).rgb;
#else
    color += emission;
#endif
#ifdef FOG
    // (ultra, CHANGE 144) the haze far off, as the window's: Panda's exponential fog mixed into the light before the
    // tone curve (so even near grass is a little hazy, as the window's is), to the light that the tone curve makes the
    // sky's colour at the horizon (fogColor: Lighting.material undoes the curve for it)
    color = mix(fogColor, color, exp(-length(vPos - camPos) * fogDensity));
#endif
    color *= exposure;
    color = max(vec3(0.0), color - vec3(0.004));
    color = (color * (vec3(6.2) * color + vec3(0.5))) / (color * (vec3(6.2) * color + vec3(1.7)) + vec3(0.06));
    gl_FragColor = vec4(color, base.a * visibility);
}`;

const DEPTH_VERT = `
precision highp float;
attribute vec3 position;
#include<instancesDeclaration>
#include<bonesDeclaration>
uniform mat4 viewProjection;
void main(void) {
#include<instancesVertex>
#include<bonesVertex>
    gl_Position = viewProjection * finalWorld * vec4(position, 1.0);
}`;

const DEPTH_FRAG = `
precision highp float;
void main(void) {
    gl_FragColor = vec4(1.0);
}`;

let registered = false;
function register() {
    if (registered) return;
    BABYLON.Effect.ShadersStore.ccpbrVertexShader = VERT;
    BABYLON.Effect.ShadersStore.ccpbrFragmentShader = FRAG;
    BABYLON.Effect.ShadersStore.ccdepthVertexShader = DEPTH_VERT;
    BABYLON.Effect.ShadersStore.ccdepthFragmentShader = DEPTH_FRAG;
    registered = true;
}

// simplepbr's tone curve on a colour (for the background: the app clears its scene buffer to the background colour
// and the tone pass curves it with everything else)
export function toneMap(rgb, exposure) {
    return rgb.map(c => {
        const x = Math.max(0, c * exposure - 0.004);
        return (x * (6.2 * x + 0.5)) / (x * (6.2 * x + 1.7) + 0.06);
    });
}

// the light toneMap turns into a colour (each channel's curve solved backwards: a quadratic; CHANGE 144, the haze)
export function untoneMap(rgb, exposure) {
    return rgb.map(y => {
        y = Math.min(0.99, Math.max(0, y));
        const a = 6.2 * (1 - y), b = 0.5 - 1.7 * y, c = -0.06 * y;
        return ((-b + Math.sqrt(b * b - 4 * a * c)) / (2 * a) + 0.004) / exposure;
    });
}

const lin = rgb => rgb.map(c => Math.pow(c, 2.2));  // screen colours (sRGB) to the linear ones lighting uses, as the app does
const bab = p => new BABYLON.Vector3(p[0], p[2], p[1]);  // a game vector in Babylon's axes

// One scene's lights, sky and shadow (made by BaseScene.build on the low, medium, high and ultra tiers).
// look: {background, exposure, ambient, sky: "env"|"sky", sun: {colour, offset, film, near, far, bias, follow,
//        ultraFilm}, spots: [{pos, at, colour, fov, att}], fill, fog}, all in game coordinates; tier: base3d's
// TIER_SETTINGS entry. (CHANGE 144) fill: [the sky's light, its reflections, the ambient light beside them] as shares
// of simplepbr's (which adds the ambient on top of the whole sky's light), envSrgb: the sky picture's colours read as
// a screen's, shScale: the spherical harmonics scaled to match (per colour): as simplepbr unless a game says (Kart Lab:
// read raw and at full strength, its sky greyed every colour on medium and high).
// fog: {colour (a screen colour), density (per metre: exponential, as Panda's)}, the haze on ultra. On ultra the
// shadow is soft and reaches ultraFilm metres across (else film), and a material may have a clear coat and the world's
// reflection (setProbe). (CHANGE 145) fog.picked: the haze only on the materials made with haze (Robot Lab's: the hall
// round the arena, as its window hazes only those)
export class Lighting {
    constructor(scene, look, tier, sh) {
        register();
        this.scene = scene;
        this.look = look;
        this.tier = tier;
        // (CHANGE 144) shScale: the sky's light from the picture read as a screen's colours, as a share of the raw
        // numbers make_textures.py worked out (a game's look may say: Kart Lab's, as its window decodes its sky)
        const k = look.shScale;
        this.sh = sh && k ? sh.map(v => v.map((c, i) => c * k[i])) : sh;
        this.materials = new Set();
        this.textures = {};
        this.exposure = Math.pow(2, look.exposure || 0);
        this.fill = look.fill || [1, 1, 1];
        this.probe = null;
        this.target = [0, 0, 0];
        this.setLights(look.spots || []);
        this.reflect = tier.ibl ? this.texture(`tex/${look.sky}_reflect.png`, false, false) : null;
        if (this.reflect) { this.reflect.wrapU = BABYLON.Texture.WRAP_ADDRESSMODE; this.reflect.wrapV = BABYLON.Texture.CLAMP_ADDRESSMODE; }
        this.brdf = tier.ibl ? this.texture("tex/brdf_lut.png", false, false) : null;
        if (this.brdf) this.brdf.wrapU = this.brdf.wrapV = BABYLON.Texture.CLAMP_ADDRESSMODE;
        this.rtt = null;
        if (tier.shadow) this.makeShadow(tier.shadow);
        scene.onBeforeRenderObservable.add(() => this.update());
    }

    texture(url, mips = true, invertY = true) {
        const key = `${url}:${mips}:${invertY}`;
        if (!this.textures[key]) {
            const make = scene => new BABYLON.Texture(url, scene, !mips, invertY,
                mips ? BABYLON.Texture.TRILINEAR_SAMPLINGMODE : BABYLON.Texture.BILINEAR_SAMPLINGMODE);
            // a copy kept for the page's life in a scene never drawn: a scene thrown away while its pictures load (an
            // arena rebuilt when the roster comes) would take the half-loaded picture with it, and the next scene's
            // copy would never be ready. With this one alive, every later copy is the loaded picture at once
            const engine = this.scene.getEngine();
            if (!engine.ccKeep) engine.ccKeep = {scene: new BABYLON.Scene(engine), textures: {}};
            if (!engine.ccKeep.textures[key]) engine.ccKeep.textures[key] = make(engine.ccKeep.scene);
            const t = make(this.scene);
            if (mips) t.anisotropicFilteringLevel = this.tier.aniso || 1;
            this.textures[key] = t;
        }
        return this.textures[key];
    }

    // the key light (index 0, the one with the shadow) and the spotlights after it
    setLights(spots) {
        const L = this.look, sun = L.sun;
        const off = sun.offset, d = Math.hypot(...off);
        const pos = [off[0] / d, off[2] / d, off[1] / d, 0], col = [...sun.colour], att = [1, 0, 0], spot = [0, 0, 0, -1];
        for (const s of spots.slice(0, 7)) {
            const p = bab(s.pos), dir = bab(s.at).subtract(p).normalize();
            pos.push(p.x, p.y, p.z, 1);
            col.push(...s.colour);
            att.push(...(s.att || [1, 0, 0]));
            spot.push(dir.x, dir.y, dir.z, Math.cos((s.fov || 40) * Math.PI / 360));
        }
        this.lights = {pos, col, att, spot, count: pos.length / 4};
        for (const m of this.materials) this.bindLights(m);
    }

    bindLights(m) {
        m.setArray4("lightPos", this.lights.pos);
        m.setArray3("lightCol", this.lights.col);
        m.setArray3("lightAtt", this.lights.att);
        m.setArray4("lightSpot", this.lights.spot);
    }

    // (ultra) a cube of the world round the kart watched (a Babylon ReflectionProbe's): materials made after this
    // with probe set reflect it
    setProbe(cube) {
        this.probe = cube;
    }

    makeShadow(size) {
        const scene = this.scene, sun = this.look.sun;
        // (ultra, CHANGE 144) further across, and as deep along the light as it is across; the bias near the same
        // distance in metres (a half again: the soft shadow's taps reach further across a slope)
        const film = this.tier.ultra && sun.ultraFilm ? sun.ultraFilm : sun.film;
        const dist = Math.hypot(...sun.offset);
        let near = sun.near, far = sun.far;
        this.shadowBias = sun.bias ?? 0.005;
        if (film !== sun.film) {
            near = Math.max(1, dist - film / 2);
            far = dist + film / 2;
            this.shadowBias *= 1.5 * (sun.far - sun.near) / (far - near);
        }
        const rtt = this.rtt = new BABYLON.RenderTargetTexture("shadow", {width: size, height: size}, scene,
            {generateMipMaps: false, generateDepthBuffer: true, noColorAttachment: true});
        rtt.createDepthStencilTexture(BABYLON.Constants.LEQUAL, true);
        const cam = this.sunCam = new BABYLON.FreeCamera("suncam", new BABYLON.Vector3(0, 50, 0), scene, false);
        cam.mode = BABYLON.Camera.ORTHOGRAPHIC_CAMERA;
        const f = film / 2;
        cam.orthoLeft = -f; cam.orthoRight = f; cam.orthoTop = f; cam.orthoBottom = -f;
        cam.minZ = near; cam.maxZ = far;
        rtt.activeCamera = cam;
        rtt.renderList = [];
        rtt.refreshRate = 1;
        this.depthMat = new BABYLON.ShaderMaterial("ccdepth", scene, {vertex: "ccdepth", fragment: "ccdepth"},
            {attributes: ["position"], uniforms: ["world", "viewProjection"]});
        this.depthMat.backFaceCulling = false;
        scene.customRenderTargets.push(rtt);
        this.shadowMatrix = BABYLON.Matrix.Identity();
    }

    addCaster(mesh) {
        if (!this.rtt || !mesh || this.rtt.renderList.includes(mesh)) return;
        this.rtt.renderList.push(mesh);
        // (a skinned mesh, Fight Lab's models: a depth material of its own, so the shared one's shader isn't
        // switched between the posed and the plain meshes every draw)
        if (mesh.skeleton && !this.depthSkinMat) {
            this.depthSkinMat = new BABYLON.ShaderMaterial("ccdepth", this.scene, {vertex: "ccdepth", fragment: "ccdepth"},
                {attributes: ["position"], uniforms: ["world", "viewProjection"]});
            this.depthSkinMat.backFaceCulling = false;
        }
        this.rtt.setMaterialForRendering(mesh, mesh.skeleton ? this.depthSkinMat : this.depthMat);
    }

    // a material: {rgb (screen colour), rough, metal, glow (emission as a share of the colour) or emission (linear, as
    // the app gives it), alpha, tex (a texture set's name)}; or a model's own (fightmodels.js, as a glTF file gives
    // it): {linear (the base colour, linear, with its alpha), rough, metal, emission, albedoUrl and mrUrl (its
    // pictures, if it has them), blend (alpha blended)}. (CHANGE 145) mrMap and glowMap: pictures already made (Robot
    // Lab's ultra robots: a texel a role, its roughness and metal, and its glow times emission, as the window's atlas);
    // haze: this one in the haze where the look's fog is picked; shadowless: no shadow looked up (what stands beyond the
    // shadow's reach)
    material(key, o) {
        const scene = this.scene, tier = this.tier;
        const defines = [`NUM_LIGHTS ${this.lights.count}`];
        const textured = !!o.tex;
        if (textured) defines.push("TEXTURED");
        if (o.albedoUrl) defines.push("ALBEDOMAP");
        if (o.mrUrl || o.mrMap) defines.push("MRMAP");
        if (o.glowMap) defines.push("GLOWMAP");
        if (textured && tier.normal) defines.push("NORMALMAP");
        if ((textured || o.mrUrl) && tier.occlusion) defines.push("OCCLUSION");
        if (tier.ibl && this.reflect) defines.push("IBL");
        if (tier.ibl && this.reflect && this.look.envSrgb) defines.push("ENVSRGB");
        const shadows = this.rtt && !o.shadowless;
        if (shadows) defines.push("SHADOWS");
        // (ultra, CHANGE 144)
        if (tier.ultra && shadows) defines.push("SOFTSHADOW");
        if (tier.ultra && this.look.fog && (!this.look.fog.picked || o.haze)) defines.push("FOG");
        if (tier.ultra && tier.ibl && this.reflect && o.clearcoat) defines.push("CLEARCOAT");
        if (tier.ultra && tier.ibl && this.reflect && o.probe && this.probe) defines.push("PROBE");
        const m = new BABYLON.ShaderMaterial(key, scene, {vertex: "ccpbr", fragment: "ccpbr"}, {
            attributes: ["position", "normal", "uv"],
            uniforms: ["world", "viewProjection", "baseColor", "emission", "roughness", "metallic", "camPos", "ambient",
                       "exposure", "visibility", "lightPos", "lightCol", "lightAtt", "lightSpot", "sh", "shadowMatrix", "shadowBias",
                       "fill", "clearcoat", "fogColor", "fogDensity"],
            samplers: ["albedoTex", "mrTex", "normalTex", "reflectTex", "brdfTex", "shadowMap", "probeTex", "glowTex"],
            defines,
            needAlphaBlending: (o.alpha ?? 1) < 1 || !!o.blend,
        });
        const c = o.linear || lin(o.rgb);
        m.setColor4("baseColor", new BABYLON.Color4(c[0], c[1], c[2], o.linear ? (o.linear[3] ?? 1) : o.alpha ?? 1));  // (one Color4: its alpha is what the canvas shows)
        const e = o.emission || (o.glow ? lin(o.rgb).map(v => v * o.glow) : [0, 0, 0]);
        m.setVector3("emission", new BABYLON.Vector3(e[0], e[1], e[2]));
        m.setFloat("roughness", o.rough);
        m.setFloat("metallic", o.metal);
        m.setFloat("exposure", this.exposure);
        m.setFloat("visibility", 1);
        m.setVector3("fill", new BABYLON.Vector3(this.fill[0], this.fill[1], this.fill[2]));
        if (defines.includes("CLEARCOAT")) m.setFloat("clearcoat", o.clearcoat);
        if (defines.includes("PROBE")) m.setTexture("probeTex", this.probe);
        if (defines.includes("FOG")) {
            const fc = untoneMap(this.look.fog.colour, this.exposure);  // (mixed in before the tone curve: CHANGE 144)
            m.setVector3("fogColor", new BABYLON.Vector3(fc[0], fc[1], fc[2]));
            m.setFloat("fogDensity", this.look.fog.density);
        }
        const amb = this.look.ambient;
        m.setVector3("ambient", new BABYLON.Vector3(amb[0], amb[1], amb[2]));
        this.bindLights(m);
        if (textured) {
            m.setTexture("albedoTex", this.texture(`tex/${o.tex}_albedo.jpg`));
            m.setTexture("mrTex", this.texture(`tex/${o.tex}_mr.jpg`));
            if (tier.normal) m.setTexture("normalTex", this.texture(`tex/${o.tex}_normal.jpg`));
        }
        // (a glTF file's pictures: its texture coordinates start at the top, so the pictures aren't turned over)
        if (o.albedoUrl) m.setTexture("albedoTex", this.texture(o.albedoUrl, true, false));
        if (o.mrUrl) m.setTexture("mrTex", this.texture(o.mrUrl, true, false));
        if (o.mrMap) m.setTexture("mrTex", o.mrMap);
        if (o.glowMap) m.setTexture("glowTex", o.glowMap);
        if (tier.ibl && this.reflect) {
            m.setArray3("sh", this.sh.flat());
            m.setTexture("reflectTex", this.reflect);
            m.setTexture("brdfTex", this.brdf);
        }
        if (shadows) {
            m.setInternalTexture("shadowMap", this.rtt.depthStencilTexture);
            m.setFloat("shadowBias", this.shadowBias);
            m.setMatrix("shadowMatrix", this.shadowMatrix);
        }
        m.backFaceCulling = false;
        // a mesh faded out (sparks, a spinner's blur): its visibility on the effect just bound
        const engine = scene.getEngine();
        m.onBindObservable.add(mesh => {
            if (mesh && mesh.visibility !== 1 && engine._currentEffect) engine._currentEffect.setFloat("visibility", mesh.visibility);
        });
        this.materials.add(m);
        m.onDisposeObservable.add(() => this.materials.delete(m));
        return m;
    }

    // where the shadow is (round the camera's target, or the arena's middle) and where the camera is
    follow(target) {
        this.target = target;
    }

    update() {
        const cam = this.scene.activeCamera;
        if (!cam) return;
        const camPos = cam.globalPosition || cam.position;
        if (this.sunCam) {
            const sun = this.look.sun, t = sun.follow === false ? [0, 0, 0] : this.target;
            const tb = new BABYLON.Vector3(t[0], t[1], t[2]);  // (Babylon axes already)
            this.sunCam.position.copyFrom(tb.add(bab(sun.offset)));
            this.sunCam.setTarget(tb);
            this.sunCam.computeWorldMatrix(true);
            this.shadowMatrix.copyFrom(this.sunCam.getViewMatrix(true).multiply(this.sunCam.getProjectionMatrix(true)));
        }
        for (const m of this.materials) {
            m.setVector3("camPos", camPos);
            if (this.sunCam) m.setMatrix("shadowMatrix", this.shadowMatrix);
        }
    }

    background() {
        return toneMap(this.look.background, this.exposure);
    }
}
