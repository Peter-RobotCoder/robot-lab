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
uniform mat4 viewProjection;
varying vec3 vPos;
varying vec3 vNormal;
varying vec2 vUV;
#ifdef VERTEXCOLOR
varying vec4 vColor;
#endif
void main(void) {
#include<instancesVertex>
    vec4 wp = finalWorld * vec4(position, 1.0);
    vPos = wp.xyz;
    vNormal = mat3(finalWorld) * normal;
    vUV = uv;
#ifdef VERTEXCOLOR
    vColor = color;
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
uniform vec4 lightPos[NUM_LIGHTS];   // xyz: the position, or the direction to the light when w is 0
uniform vec3 lightCol[NUM_LIGHTS];
uniform vec3 lightAtt[NUM_LIGHTS];   // constant, linear, quadratic
uniform vec4 lightSpot[NUM_LIGHTS];  // xyz: a spotlight's direction, w: the cosine of its cut-off (-1: not a spot)
#ifdef TEXTURED
uniform sampler2D albedoTex;
uniform sampler2D mrTex;
#endif
#ifdef NORMALMAP
uniform sampler2D normalTex;
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
varying vec3 vPos;
varying vec3 vNormal;
varying vec2 vUV;
#ifdef VERTEXCOLOR
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
    return mix(a, b, lod - l0);
}
#endif

#ifdef SHADOWS
float shadowAt(vec3 p) {
    vec4 s = shadowMatrix * vec4(p, 1.0);
    vec3 c = s.xyz / s.w;
    vec2 uv = c.xy * 0.5 + 0.5;
    if (uv.x <= 0.0 || uv.x >= 1.0 || uv.y <= 0.0 || uv.y >= 1.0 || c.z >= 1.0) return 1.0;
    return texture(shadowMap, vec3(uv, c.z * 0.5 + 0.5 - shadowBias));
}
#endif

void main(void) {
    vec4 mr = vec4(1.0);
    vec4 albedo = vec4(1.0);
#ifdef TEXTURED
    mr = texture2D(mrTex, vUV);
    albedo = texture2D(albedoTex, vUV);
    albedo.rgb = pow(albedo.rgb, vec3(2.2));  // (an sRGB picture, as the app loads it)
#endif
    float metal = clamp(metallic * mr.b, 0.0, 1.0);
    float prough = clamp(roughness * mr.g, 0.0, 1.0);
    float arough = prough * prough;
    vec4 base = baseColor * albedo;
#ifdef VERTEXCOLOR
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
    }
#ifdef IBL
    vec3 gn = vec3(n.x, n.z, n.y);
    vec3 iblF = specColor + (max(vec3(1.0 - prough), specColor) - specColor) * pow(clamp(1.0 - ndotv, 0.0, 1.0), 5.0);
    vec3 kd = (1.0 - iblF) * (1.0 - metal);
    vec3 iblDiff = base.rgb * max(irradianceFromSh(gn), 0.0) / PI;
    vec3 r = reflect(-v, n);
    vec2 envBrdf = texture2D(brdfTex, vec2(ndotv, prough)).rg;
    vec3 iblSpec = envLookup(vec3(r.x, r.z, r.y), prough * 4.0) * (iblF * envBrdf.x + envBrdf.y);
    color += (kd * iblDiff + iblSpec) * ao;
#endif
    color += (diffuseColor + specColor) * ambient * ao;
    color += emission;
    color *= exposure;
    color = max(vec3(0.0), color - vec3(0.004));
    color = (color * (vec3(6.2) * color + vec3(0.5))) / (color * (vec3(6.2) * color + vec3(1.7)) + vec3(0.06));
    gl_FragColor = vec4(color, base.a * visibility);
}`;

const DEPTH_VERT = `
precision highp float;
attribute vec3 position;
#include<instancesDeclaration>
uniform mat4 viewProjection;
void main(void) {
#include<instancesVertex>
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

const lin = rgb => rgb.map(c => Math.pow(c, 2.2));  // screen colours (sRGB) to the linear ones lighting uses, as the app does
const bab = p => new BABYLON.Vector3(p[0], p[2], p[1]);  // a game vector in Babylon's axes

// One scene's lights, sky and shadow (made by BaseScene.build on the low, medium and high tiers).
// look: {background, exposure, ambient, sky: "env"|"sky", sun: {colour, offset, film, near, far, bias, follow},
//        spots: [{pos, at, colour, fov, att}]}, all in game coordinates; tier: base3d's TIER_SETTINGS entry
export class Lighting {
    constructor(scene, look, tier, sh) {
        register();
        this.scene = scene;
        this.look = look;
        this.tier = tier;
        this.sh = sh;
        this.materials = new Set();
        this.textures = {};
        this.exposure = Math.pow(2, look.exposure || 0);
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

    makeShadow(size) {
        const scene = this.scene, sun = this.look.sun;
        const rtt = this.rtt = new BABYLON.RenderTargetTexture("shadow", {width: size, height: size}, scene,
            {generateMipMaps: false, generateDepthBuffer: true, noColorAttachment: true});
        rtt.createDepthStencilTexture(BABYLON.Constants.LEQUAL, true);
        const cam = this.sunCam = new BABYLON.FreeCamera("suncam", new BABYLON.Vector3(0, 50, 0), scene, false);
        cam.mode = BABYLON.Camera.ORTHOGRAPHIC_CAMERA;
        const f = sun.film / 2;
        cam.orthoLeft = -f; cam.orthoRight = f; cam.orthoTop = f; cam.orthoBottom = -f;
        cam.minZ = sun.near; cam.maxZ = sun.far;
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
        this.rtt.setMaterialForRendering(mesh, this.depthMat);
    }

    // a material: {rgb (screen colour), rough, metal, glow (emission as a share of the colour) or emission (linear, as
    // the app gives it), alpha, tex (a texture set's name)}
    material(key, o) {
        const scene = this.scene, tier = this.tier;
        const defines = [`NUM_LIGHTS ${this.lights.count}`];
        const textured = !!o.tex;
        if (textured) defines.push("TEXTURED");
        if (textured && tier.normal) defines.push("NORMALMAP");
        if (textured && tier.occlusion) defines.push("OCCLUSION");
        if (tier.ibl && this.reflect) defines.push("IBL");
        if (this.rtt) defines.push("SHADOWS");
        const m = new BABYLON.ShaderMaterial(key, scene, {vertex: "ccpbr", fragment: "ccpbr"}, {
            attributes: ["position", "normal", "uv"],
            uniforms: ["world", "viewProjection", "baseColor", "emission", "roughness", "metallic", "camPos", "ambient",
                       "exposure", "visibility", "lightPos", "lightCol", "lightAtt", "lightSpot", "sh", "shadowMatrix", "shadowBias"],
            samplers: ["albedoTex", "mrTex", "normalTex", "reflectTex", "brdfTex", "shadowMap"],
            defines,
            needAlphaBlending: (o.alpha ?? 1) < 1,
        });
        const c = lin(o.rgb);
        m.setColor4("baseColor", new BABYLON.Color3(c[0], c[1], c[2]), o.alpha ?? 1);
        const e = o.emission || (o.glow ? lin(o.rgb).map(v => v * o.glow) : [0, 0, 0]);
        m.setVector3("emission", new BABYLON.Vector3(e[0], e[1], e[2]));
        m.setFloat("roughness", o.rough);
        m.setFloat("metallic", o.metal);
        m.setFloat("exposure", this.exposure);
        m.setFloat("visibility", 1);
        const amb = this.look.ambient;
        m.setVector3("ambient", new BABYLON.Vector3(amb[0], amb[1], amb[2]));
        this.bindLights(m);
        if (textured) {
            m.setTexture("albedoTex", this.texture(`tex/${o.tex}_albedo.jpg`));
            m.setTexture("mrTex", this.texture(`tex/${o.tex}_mr.jpg`));
            if (tier.normal) m.setTexture("normalTex", this.texture(`tex/${o.tex}_normal.jpg`));
        }
        if (tier.ibl && this.reflect) {
            m.setArray3("sh", this.sh.flat());
            m.setTexture("reflectTex", this.reflect);
            m.setTexture("brdfTex", this.brdf);
        }
        if (this.rtt) {
            m.setInternalTexture("shadowMap", this.rtt.depthStencilTexture);
            m.setFloat("shadowBias", this.look.sun.bias ?? 0.005);
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
