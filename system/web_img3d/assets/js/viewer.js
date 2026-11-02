import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export class ModelViewer {
    constructor(element, onError) {
        this.element = element;
        this.onError = onError;
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.model = null;
        this.animationFrame = null;
        this.loadController = null;
        this.loadToken = 0;
        this.handleResize = this.resize.bind(this);
    }

    initialize() {
        if (this.renderer) {
            return;
        }

        this.element.replaceChildren();

        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0xeeeeee);

        const width = this.element.clientWidth;
        const height = this.element.clientHeight;
        this.camera = new THREE.PerspectiveCamera(
            45,
            width / height,
            0.01,
            10000
        );

        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.setSize(width, height);
        this.renderer.outputColorSpace = THREE.SRGBColorSpace;
        this.element.appendChild(this.renderer.domElement);

        this.controls = new OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.screenSpacePanning = true;
        this.controls.minDistance = 0.01;
        this.controls.maxDistance = 10000;

        this.scene.add(new THREE.AmbientLight(0xffffff, 2));

        const keyLight = new THREE.DirectionalLight(0xffffff, 3);
        keyLight.position.set(5, 10, 5);
        this.scene.add(keyLight);

        const fillLight = new THREE.DirectionalLight(0xffffff, 1);
        fillLight.position.set(-5, 5, -5);
        this.scene.add(fillLight);

        const animate = () => {
            this.animationFrame = requestAnimationFrame(animate);
            this.controls.update();
            this.renderer.render(this.scene, this.camera);
        };

        animate();
        window.addEventListener('resize', this.handleResize);
    }

    resize() {
        if (!this.renderer || !this.camera) {
            return;
        }

        const width = this.element.clientWidth;
        const height = this.element.clientHeight;

        if (width <= 0 || height <= 0) {
            return;
        }

        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    fitToModel(model) {
        const bounds = new THREE.Box3().setFromObject(model);
        const size = bounds.getSize(new THREE.Vector3());
        const center = bounds.getCenter(new THREE.Vector3());

        model.position.sub(center);

        const maxSize = Math.max(size.x, size.y, size.z);
        if (!Number.isFinite(maxSize) || maxSize <= 0) {
            this.camera.position.set(0, 0, 5);
            this.camera.lookAt(0, 0, 0);
            return;
        }

        const fov = THREE.MathUtils.degToRad(this.camera.fov);
        const distance = maxSize / (2 * Math.tan(fov / 2));

        this.camera.position.set(
            distance * 0.8,
            distance * 0.5,
            distance * 1.5
        );
        this.camera.near = Math.max(maxSize / 10000, 0.001);
        this.camera.far = Math.max(maxSize * 100, 100);
        this.camera.updateProjectionMatrix();
        this.controls.target.set(0, 0, 0);
        this.controls.update();
    }

    async load(sessionId) {
        return this.loadUrl(
            `get-glb.php?sessionId=${encodeURIComponent(sessionId)}`
        );
    }

    async loadUrl(url) {
        this.cancelPendingLoad();
        const token = ++this.loadToken;
        const controller = new AbortController();
        this.loadController = controller;
        try {
            const response = await fetch(url, {
                method: 'GET',
                cache: 'no-store',
                signal: controller.signal
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const glbData = await response.arrayBuffer();
            if (token !== this.loadToken) return false;
            this.initialize();

            const loader = new GLTFLoader();
            const gltf = await new Promise((resolve, reject) => {
                loader.parse(glbData, '', resolve, reject);
            });

            if (token !== this.loadToken) {
                this.disposeModel(gltf.scene);
                return false;
            }

            if (!this.renderer) {
                this.initialize();
            }
            if (this.model) {
                this.scene.remove(this.model);
                this.disposeModel(this.model);
            }

            this.model = gltf.scene;
            this.scene.add(this.model);
            this.fitToModel(this.model);
            return true;
        } catch (error) {
            if (error.name === 'AbortError' || token !== this.loadToken) return false;
            console.error('Could not load GLB model:', error);
            this.onError(error);
            return false;
        } finally {
            if (token === this.loadToken) this.loadController = null;
        }
    }

    cancelPendingLoad() {
        this.loadToken += 1;
        if (this.loadController) {
            this.loadController.abort();
            this.loadController = null;
        }
    }

    disposeModel(model) {
        const geometries = new Set();
        const materials = new Set();
        const textures = new Set();

        const collectTextures = (value, visited = new Set()) => {
            if (!value || typeof value !== 'object' || visited.has(value)) {
                return;
            }
            if (value.isTexture) {
                textures.add(value);
                return;
            }

            visited.add(value);
            for (const nestedValue of Object.values(value)) {
                collectTextures(nestedValue, visited);
            }
        };

        model.traverse((object) => {
            if (object.geometry) {
                geometries.add(object.geometry);
            }

            const objectMaterials = Array.isArray(object.material)
                ? object.material
                : object.material ? [object.material] : [];
            for (const material of objectMaterials) {
                if (!material) continue;
                materials.add(material);
                collectTextures(material);
            }
        });

        for (const geometry of geometries) geometry.dispose();
        for (const material of materials) material.dispose();
        for (const texture of textures) texture.dispose();
    }

    dispose() {
        this.cancelPendingLoad();

        if (this.model) {
            if (this.scene) this.scene.remove(this.model);
            this.disposeModel(this.model);
            this.model = null;
        }

        if (this.animationFrame !== null) {
            cancelAnimationFrame(this.animationFrame);
            this.animationFrame = null;
        }

        if (this.renderer) {
            this.renderer.domElement.remove();
            this.renderer.dispose();
            this.renderer = null;
        }

        if (this.controls) {
            this.controls.dispose();
            this.controls = null;
        }

        this.scene = null;
        this.camera = null;
        window.removeEventListener('resize', this.handleResize);
    }
}
