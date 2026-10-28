# Three.js

Version: 0.164.1 (MIT license, see LICENSE).

These files are copied from the published three npm package. The minified
ES module build is served as build/three.module.js. Included addons are
GLTFLoader, OrbitControls, and BufferGeometryUtils.

The digital twin uses these local files rather than runtime CDN imports.
Models requiring optional Draco or KTX2 decoders fall back to the built-in
equipment geometry when those decoders are unavailable.
