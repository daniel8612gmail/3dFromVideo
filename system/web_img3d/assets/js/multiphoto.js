import { ModelViewer } from './viewer.js';

const API = 'api/v1/';
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;
const MAX_METADATA_BYTES = 64 * 1024;
const REQUIRED_METADATA_FIELDS = [
    'frameId', 'sequence', 'timestampMs', 'trackingState', 'assetId', 'sha256',
    'mimeType', 'width', 'height', 'orientation', 'imageTransform',
    'arSessionEpochId', 'referenceFrameId', 'cameraToFirstFrame',
    'intrinsics', 'distortionStatus', 'cameraProfile'
];
const RESERVED_METADATA_FIELDS = [
    'systemSessionId', 'mogeToCameraMatrix4x4', 'scaleEstimate', 'axes',
    'metadataCanonical', 'imageFile', 'status', 'progress', 'attempts', 'createdAt'
];

const el = {
    deviceId: document.getElementById('device-id'),
    createSession: document.getElementById('create-session'),
    openSessionId: document.getElementById('open-session-id'),
    openSession: document.getElementById('open-session'),
    connectionState: document.getElementById('connection-state'),
    sessionSummary: document.getElementById('session-summary'),
    activeSessionId: document.getElementById('active-session-id'),
    sessionStatus: document.getElementById('session-status'),
    currentVersion: document.getElementById('current-version'),
    completeSession: document.getElementById('complete-session'),
    imageFiles: document.getElementById('image-files'),
    uploadAll: document.getElementById('upload-all'),
    refreshStatus: document.getElementById('refresh-status'),
    uploadMessage: document.getElementById('upload-message'),
    queueCount: document.getElementById('queue-count'),
    frameQueue: document.getElementById('frame-queue'),
    serverFrames: document.getElementById('server-frames'),
    modelViewer: document.getElementById('model-viewer'),
    modelMessage: document.getElementById('model-message'),
    downloadModel: document.getElementById('download-model'),
    retryModel: document.getElementById('retry-model'),
    globalError: document.getElementById('global-error')
};

const queuesBySession = new Map();
const statusBySession = new Map();
const loadedModel = { sessionId: null, version: 0 };
const failedModelKey = { sessionId: null, version: 0 };
let activeSessionId = null;
let activeSession = null;
let polling = false;
let switchingSession = false;
let batchRunning = false;
let previewLoadToken = 0;

const viewer = new ModelViewer(el.modelViewer, (error) => {
    console.warn('Model preview could not be loaded:', error);
});

function randomDeviceId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
        return `web-${window.crypto.randomUUID()}`;
    }
    const bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    return `web-${Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')}`;
}

function queueFor(sessionId = activeSessionId) {
    if (!sessionId) return [];
    if (!queuesBySession.has(sessionId)) queuesBySession.set(sessionId, []);
    return queuesBySession.get(sessionId);
}

function showError(message) {
    el.globalError.textContent = message;
    el.globalError.hidden = false;
}

function clearError() {
    el.globalError.textContent = '';
    el.globalError.hidden = true;
}

function apiError(response, payload) {
    if (payload && typeof payload.error === 'string' && payload.error.trim()) {
        return payload.error.slice(0, 500);
    }
    return `Żądanie API nie powiodło się (HTTP ${response.status}).`;
}

async function requestJson(url, options = {}) {
    let response;
    try {
        response = await fetch(url, { cache: 'no-store', ...options });
    } catch (error) {
        throw new Error('Nie można połączyć się z API. Sprawdź połączenie i spróbuj ponownie.');
    }
    let payload = null;
    try {
        payload = await response.json();
    } catch (error) {
        // Nie wyświetlamy surowego HTML ani wewnętrznych treści odpowiedzi serwera.
    }
    if (!response.ok || !payload || payload.success !== true) {
        throw new Error(apiError(response, payload));
    }
    return payload;
}

function stableStringify(value) {
    if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
    if (value && typeof value === 'object') {
        return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`;
    }
    return JSON.stringify(value);
}

function isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function binaryMime(bytes) {
    if (bytes.length >= 8
        && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47
        && bytes[4] === 0x0d && bytes[5] === 0x0a && bytes[6] === 0x1a && bytes[7] === 0x0a) {
        return 'image/png';
    }
    if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
        return 'image/jpeg';
    }
    if (bytes.length >= 12
        && String.fromCharCode(...bytes.slice(0, 4)) === 'RIFF'
        && String.fromCharCode(...bytes.slice(8, 12)) === 'WEBP') {
        return 'image/webp';
    }
    return null;
}

function imageDimensions(bytes, mime) {
    if (mime === 'image/png') {
        if (bytes.length < 24) throw new Error('Nagłówek PNG jest niekompletny.');
        const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
        return { width: view.getUint32(16), height: view.getUint32(20) };
    }
    if (mime === 'image/jpeg') {
        let offset = 2;
        const frameMarkers = new Set([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf]);
        while (offset + 3 < bytes.length) {
            if (bytes[offset] !== 0xff) {
                offset += 1;
                continue;
            }
            while (offset < bytes.length && bytes[offset] === 0xff) offset += 1;
            const marker = bytes[offset++];
            if (marker === 0xd9 || marker === 0xda) break;
            if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) continue;
            if (offset + 1 >= bytes.length) break;
            const segmentLength = (bytes[offset] << 8) | bytes[offset + 1];
            if (segmentLength < 2 || offset + segmentLength > bytes.length) break;
            if (frameMarkers.has(marker)) {
                if (segmentLength < 7) break;
                return {
                    height: (bytes[offset + 3] << 8) | bytes[offset + 4],
                    width: (bytes[offset + 5] << 8) | bytes[offset + 6]
                };
            }
            offset += segmentLength;
        }
        throw new Error('Nie można odczytać wymiarów JPEG z oryginalnych bajtów.');
    }
    if (mime === 'image/webp') {
        if (bytes.length < 30) throw new Error('Nagłówek WebP jest niekompletny.');
        let offset = 12;
        while (offset + 8 <= bytes.length) {
            const chunk = String.fromCharCode(...bytes.slice(offset, offset + 4));
            const chunkSize = new DataView(bytes.buffer, bytes.byteOffset + offset + 4, 4).getUint32(0, true);
            const data = offset + 8;
            if (data + chunkSize > bytes.length) break;
            if (chunk === 'VP8X' && chunkSize >= 10) {
                return {
                    width: 1 + bytes[data + 4] + (bytes[data + 5] << 8) + (bytes[data + 6] << 16),
                    height: 1 + bytes[data + 7] + (bytes[data + 8] << 8) + (bytes[data + 9] << 16)
                };
            }
            if (chunk === 'VP8 ' && chunkSize >= 10
                && bytes[data + 3] === 0x9d && bytes[data + 4] === 0x01 && bytes[data + 5] === 0x2a) {
                const view = new DataView(bytes.buffer, bytes.byteOffset + data + 6, 4);
                return { width: view.getUint16(0, true) & 0x3fff, height: view.getUint16(2, true) & 0x3fff };
            }
            if (chunk === 'VP8L' && chunkSize >= 5 && bytes[data] === 0x2f) {
                const b1 = bytes[data + 1], b2 = bytes[data + 2], b3 = bytes[data + 3], b4 = bytes[data + 4];
                return {
                    width: 1 + b1 + ((b2 & 0x3f) << 8),
                    height: 1 + ((b2 >> 6) | (b3 << 2) | ((b4 & 0x0f) << 10))
                };
            }
            offset = data + chunkSize + (chunkSize % 2);
        }
        throw new Error('Nie można odczytać wymiarów WebP z oryginalnych bajtów.');
    }
    throw new Error('Obsługiwane są tylko obrazy JPEG, PNG i WebP.');
}

async function inspectFile(file) {
    if (!file || file.size < 1 || file.size > MAX_IMAGE_BYTES) {
        throw new Error('Każdy obraz musi mieć rozmiar od 1 bajta do 20 MiB.');
    }
    const buffer = await file.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    const mimeType = binaryMime(bytes);
    if (!mimeType) throw new Error('Nie rozpoznano JPEG, PNG ani WebP w bajtach pliku.');
    if (file.type && file.type !== mimeType) {
        throw new Error(`Typ pliku przeglądarki (${file.type}) nie zgadza się z typem obrazu (${mimeType}).`);
    }
    const dimensions = imageDimensions(bytes, mimeType);
    if (!dimensions.width || !dimensions.height
        || dimensions.width > 32768 || dimensions.height > 32768
        || dimensions.width * dimensions.height > 100000000) {
        throw new Error('Obraz ma nieprawidłowe lub niedozwolone wymiary.');
    }
    if (!window.crypto || !window.crypto.subtle) {
        throw new Error('Web Crypto jest niedostępne. Otwórz tę stronę przez HTTPS lub localhost.');
    }
    const digest = await window.crypto.subtle.digest('SHA-256', buffer);
    const sha256 = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
    return { mimeType, ...dimensions, sha256 };
}

function parseMetadata(raw) {
    if (new TextEncoder().encode(raw).byteLength > MAX_METADATA_BYTES) {
        throw new Error('JSON metadanych przekracza limit API 64 KiB.');
    }
    let metadata;
    try {
        metadata = JSON.parse(raw);
    } catch (error) {
        throw new Error('Metadane nie są poprawnym JSON-em.');
    }
    if (!isPlainObject(metadata)) throw new Error('Metadane muszą być obiektem JSON.');
    const actualFields = Object.keys(metadata);
    const missing = REQUIRED_METADATA_FIELDS.filter((field) => !Object.prototype.hasOwnProperty.call(metadata, field));
    if (missing.length) throw new Error(`Brak wymaganych pól: ${missing.join(', ')}.`);
    const reserved = actualFields.filter((field) => RESERVED_METADATA_FIELDS.includes(field));
    if (reserved.length) {
        throw new Error(`Pola zarezerwowane lub konwencja modelu nie mogą pochodzić od klienta: ${reserved.join(', ')}.`);
    }
    if (typeof metadata.frameId !== 'string' || !/^[A-Za-z0-9_-]{1,96}$/.test(metadata.frameId)) {
        throw new Error('frameId musi mieć 1–96 znaków: litery, cyfry, _ lub -.');
    }
    if (!Number.isSafeInteger(metadata.sequence) || metadata.sequence < 0 || metadata.sequence > 2147483647) {
        throw new Error('sequence musi być nieujemną liczbą całkowitą.');
    }
    if (!Number.isSafeInteger(metadata.timestampMs) || metadata.timestampMs < 1
        || metadata.timestampMs > Number.MAX_SAFE_INTEGER) {
        throw new Error('timestampMs musi być dodatnią liczbą całkowitą.');
    }
    for (const name of ['assetId', 'arSessionEpochId', 'referenceFrameId']) {
        if (typeof metadata[name] !== 'string' || !metadata[name].trim()
            || new TextEncoder().encode(metadata[name]).byteLength > 128) {
            throw new Error(`${name} musi być tekstem o długości 1–128 bajtów.`);
        }
    }
    if (!['TRACKING', 'PAUSED', 'STOPPED', 'LIMITED'].includes(metadata.trackingState)) {
        throw new Error('trackingState musi być TRACKING, PAUSED, STOPPED lub LIMITED.');
    }
    if (!/^[a-f0-9]{64}$/.test(metadata.sha256)) throw new Error('sha256 musi być 64 małymi znakami hex.');
    if (!Number.isSafeInteger(metadata.width) || !Number.isSafeInteger(metadata.height)
        || metadata.width < 1 || metadata.height < 1) {
        throw new Error('width i height muszą być dodatnimi liczbami całkowitymi.');
    }
    if (![0, 90, 180, 270].includes(metadata.orientation)) {
        throw new Error('orientation musi wynosić 0, 90, 180 lub 270.');
    }
    if (!isPlainObject(metadata.imageTransform)
        || !isPlainObject(metadata.imageTransform.crop)
        || !Number.isSafeInteger(metadata.imageTransform.sourceWidth)
        || !Number.isSafeInteger(metadata.imageTransform.sourceHeight)
        || ![0, 90, 180, 270].includes(metadata.imageTransform.rotationDegrees)
        || typeof metadata.imageTransform.mirrorX !== 'boolean') {
        throw new Error('imageTransform musi jawnie opisywać źródło, crop, obrót i odbicie.');
    }
    const crop = metadata.imageTransform.crop;
    if (!['x', 'y', 'width', 'height'].every((key) => Number.isFinite(crop[key]))
        || crop.x < 0 || crop.y < 0 || crop.width <= 0 || crop.height <= 0
        || crop.x + crop.width > 1 || crop.y + crop.height > 1) {
        throw new Error('imageTransform.crop musi być prawidłowym znormalizowanym cropem.');
    }
    if (Object.prototype.hasOwnProperty.call(metadata, 'cameraToSystemSessionFrame')) {
        throw new Error('cameraToSystemSessionFrame jest nieobsługiwane. Podaj jawne cameraToFirstFrame w układzie całego skanu.');
    }
    if (!isPlainObject(metadata.cameraToFirstFrame)
        || !Array.isArray(metadata.cameraToFirstFrame.translationM)
        || !Array.isArray(metadata.cameraToFirstFrame.rotationQuaternionXyzw)
        || metadata.cameraToFirstFrame.translationM.length !== 3
        || metadata.cameraToFirstFrame.rotationQuaternionXyzw.length !== 4
        || !metadata.cameraToFirstFrame.translationM.every(Number.isFinite)
        || !metadata.cameraToFirstFrame.rotationQuaternionXyzw.every(Number.isFinite)) {
        throw new Error('cameraToFirstFrame musi zawierać translationM [x,y,z] i rotationQuaternionXyzw [x,y,z,w].');
    }
    const translation = metadata.cameraToFirstFrame.translationM;
    const quaternion = metadata.cameraToFirstFrame.rotationQuaternionXyzw;
    if (Math.abs(Math.hypot(...quaternion) - 1) > 0.001) {
        throw new Error('Quaternion xyzw musi być znormalizowany.');
    }
    if (metadata.sequence === 0
        && (translation.some((value) => Math.abs(value) > 0.000001)
            || quaternion.slice(0, 3).some((value) => Math.abs(value) > 0.001)
            || Math.abs(Math.abs(quaternion[3]) - 1) > 0.001)) {
        throw new Error('Klatka sequence 0 musi mieć tożsamościowe cameraToFirstFrame: translację [0,0,0] i quaternion [0,0,0,±1].');
    }
    if (!isPlainObject(metadata.intrinsics)
        || !['fx', 'fy', 'cx', 'cy'].every((key) => Number.isFinite(metadata.intrinsics[key]))) {
        throw new Error('intrinsics musi zawierać skończone fx, fy, cx i cy.');
    }
    if (metadata.distortionStatus !== 'not_provided') {
        throw new Error('API v1 przyjmuje wyłącznie distortionStatus: "not_provided".');
    }
    if (!isPlainObject(metadata.cameraProfile) || Object.keys(metadata.cameraProfile).length === 0) {
        throw new Error('cameraProfile musi być niepustym obiektem JSON.');
    }
    return metadata;
}

function existingLocalMetadata(queue, exceptItem) {
    return queue.flatMap((item) => {
        if (item === exceptItem) return [];
        if (item.snapshot) return [item.snapshot.metadata];
        try {
            return item.metadataText.trim() ? [parseMetadata(item.metadataText)] : [];
        } catch (error) {
            return [];
        }
    });
}

async function validateFrame(item, queue) {
    if (!item.file) throw new Error('Brak pliku obrazu.');
    if (!item.metadataText.trim()) throw new Error('Zaimportuj lub wklej JSON metadanych dla tego obrazu.');
    const metadata = parseMetadata(item.metadataText);
    const inspected = await inspectFile(item.file);
    if (metadata.sha256 !== inspected.sha256) {
        throw new Error('SHA-256 metadanych nie odpowiada dokładnym bajtom wybranego pliku.');
    }
    if (metadata.mimeType !== inspected.mimeType) {
        throw new Error('mimeType metadanych nie odpowiada typowi obrazu odczytanemu z bajtów.');
    }
    if (metadata.width !== inspected.width || metadata.height !== inspected.height) {
        throw new Error(`Wymiary JSON (${metadata.width}×${metadata.height}) nie odpowiadają obrazowi (${inspected.width}×${inspected.height}).`);
    }
    const localMetadata = existingLocalMetadata(queue, item);
    const duplicateFrame = localMetadata.find((other) => other.frameId === metadata.frameId);
    if (duplicateFrame) throw new Error(`frameId ${metadata.frameId} jest już użyty w tej lokalnej kolejce.`);
    if (localMetadata.some((other) => other.sequence === metadata.sequence)) {
        throw new Error(`sequence ${metadata.sequence} jest już użyty w tej lokalnej kolejce.`);
    }
    const previous = localMetadata[0];
    if (previous && stableStringify(previous.cameraProfile) !== stableStringify(metadata.cameraProfile)) {
        throw new Error('cameraProfile różni się od profilu pozostałych klatek w tej kolejce.');
    }
    const serverFrames = statusBySession.get(activeSessionId)?.frames || [];
    if (serverFrames.some((frame) => frame.frameId === metadata.frameId)) {
        throw new Error(`frameId ${metadata.frameId} istnieje już na serwerze. Użyj ponownie tej samej lokalnej klatki albo wybierz nową klatkę z jej własnym frameId.`);
    }
    if (serverFrames.some((frame) => Number(frame.sequence) === metadata.sequence)) {
        throw new Error(`sequence ${metadata.sequence} istnieje już na serwerze.`);
    }
    return metadata;
}

function setRowState(item, state, message = '') {
    item.state = state;
    item.error = message;
    renderQueue();
}

function renderQueue() {
    const queue = queueFor();
    el.frameQueue.replaceChildren();
    el.queueCount.textContent = `${queue.length} ${queue.length === 1 ? 'obraz' : 'obrazów'}`;
    el.uploadAll.disabled = !activeSessionId || !canAcceptFrames() || queue.length === 0
        || batchRunning
        || queue.some((item) => item.state === 'uploading' || item.state === 'validating');

    queue.forEach((item, index) => {
        const card = document.createElement('article');
        card.className = 'frame-card';

        const image = document.createElement('img');
        image.className = 'frame-preview';
        image.src = item.previewUrl;
        image.alt = `Podgląd ${item.file.name}`;
        card.appendChild(image);

        const content = document.createElement('div');
        content.className = 'frame-content';
        const title = document.createElement('div');
        title.className = 'frame-title';
        const filename = document.createElement('strong');
        filename.textContent = item.file.name;
        const size = document.createElement('span');
        size.className = 'subtle';
        size.textContent = `${(item.file.size / (1024 * 1024)).toFixed(2)} MiB`;
        title.append(filename, size);
        content.appendChild(title);

        const metadataLabel = document.createElement('label');
        metadataLabel.textContent = item.snapshot
            ? 'JSON metadanych (zablokowany dla retry dokładnie tej samej klatki)'
            : 'JSON metadanych dla tego obrazu';
        const textarea = document.createElement('textarea');
        textarea.spellcheck = false;
        textarea.autocapitalize = 'off';
        textarea.autocomplete = 'off';
        textarea.setAttribute('aria-label', `Metadane JSON dla ${item.file.name}`);
        textarea.placeholder = 'Wklej tutaj kompletny obiekt metadata v1 dostarczony przez zewnętrzne źródło.';
        textarea.value = item.metadataText;
        textarea.readOnly = Boolean(item.snapshot) || item.state === 'validating' || item.state === 'uploading';
        textarea.addEventListener('input', () => { item.metadataText = textarea.value; });
        metadataLabel.appendChild(textarea);
        content.appendChild(metadataLabel);

        const actions = document.createElement('div');
        actions.className = 'frame-actions';
        const importLabel = document.createElement('label');
        importLabel.className = 'button metadata-import';
        importLabel.textContent = 'Importuj JSON';
        const metadataFile = document.createElement('input');
        metadataFile.type = 'file';
        metadataFile.accept = '.json,application/json,text/json';
        metadataFile.setAttribute('aria-label', `Importuj JSON metadanych dla ${item.file.name}`);
        metadataFile.disabled = Boolean(item.snapshot)
            || item.state === 'validating' || item.state === 'uploading';
        metadataFile.addEventListener('change', async () => {
            const file = metadataFile.files && metadataFile.files[0];
            if (!file) return;
            if (file.size > MAX_METADATA_BYTES) {
                setRowState(item, 'error', 'JSON metadanych przekracza limit 64 KiB.');
                return;
            }
            try {
                item.metadataText = await file.text();
                item.error = '';
                renderQueue();
            } catch (error) {
                setRowState(item, 'error', 'Nie można odczytać pliku JSON metadanych.');
            }
        });
        importLabel.appendChild(metadataFile);
        actions.appendChild(importLabel);

        const uploadButton = document.createElement('button');
        uploadButton.type = 'button';
        uploadButton.className = 'button button-primary';
        uploadButton.textContent = item.snapshot ? 'Ponów tę samą klatkę' : 'Sprawdź i wyślij';
        uploadButton.disabled = !activeSessionId || !canAcceptFrames()
            || batchRunning || item.state === 'uploading' || item.state === 'validating';
        uploadButton.addEventListener('click', () => uploadFrame(item));
        actions.appendChild(uploadButton);

        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.className = 'button';
        removeButton.textContent = 'Usuń';
        removeButton.disabled = item.state === 'uploading' || item.state === 'validating';
        removeButton.setAttribute('aria-label', `Usuń ${item.file.name} z kolejki`);
        removeButton.addEventListener('click', () => {
            URL.revokeObjectURL(item.previewUrl);
            queue.splice(index, 1);
            renderQueue();
        });
        actions.appendChild(removeButton);
        content.appendChild(actions);

        const progress = document.createElement('div');
        progress.className = 'frame-progress';
        progress.setAttribute('role', 'progressbar');
        progress.setAttribute('aria-label', `Postęp uploadu ${item.file.name}`);
        progress.setAttribute('aria-valuemin', '0');
        progress.setAttribute('aria-valuemax', '100');
        const fill = document.createElement('span');
        fill.style.width = `${Math.max(0, Math.min(100, Number(item.uploadProgress) || 0))}%`;
        progress.setAttribute('aria-valuenow', String(Math.max(0, Math.min(100, Number(item.uploadProgress) || 0))));
        progress.appendChild(fill);
        content.appendChild(progress);

        const status = document.createElement('p');
        status.className = 'subtle';
        status.textContent = item.statusMessage || (
            item.snapshot ? 'Gotowa do ponowienia z tym samym frameId, SHA-256 i JSON-em.' : 'Wymagany JSON metadanych zewnętrznego źródła.'
        );
        content.appendChild(status);
        if (item.error) {
            const error = document.createElement('p');
            error.className = 'frame-error';
            error.setAttribute('role', 'alert');
            error.textContent = item.error;
            content.appendChild(error);
        }
        card.appendChild(content);
        el.frameQueue.appendChild(card);
    });
}

function canAcceptFrames() {
    return Boolean(activeSessionId && activeSession
        && activeSession.session && activeSession.session.acceptingFrames === true
        && activeSession.session.status !== 'error');
}

function renderSessionControls() {
    const connected = Boolean(activeSessionId);
    el.connectionState.textContent = connected ? 'Połączono' : 'Brak aktywnej sesji';
    el.sessionSummary.hidden = !connected;
    el.imageFiles.disabled = !connected || !canAcceptFrames();
    el.refreshStatus.disabled = !connected;
    el.completeSession.disabled = !connected || !canAcceptFrames();
    if (connected) {
        el.activeSessionId.textContent = activeSessionId;
        el.sessionStatus.textContent = activeSession?.session?.status || '—';
        el.currentVersion.textContent = String(activeSession?.session?.currentVersion || 0);
    }
    renderQueue();
}

function renderServerFrames(frames) {
    el.serverFrames.replaceChildren();
    if (!Array.isArray(frames) || frames.length === 0) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 5;
        cell.className = 'empty-state';
        cell.textContent = 'Brak przesłanych klatek w tej sesji.';
        row.appendChild(cell);
        el.serverFrames.appendChild(row);
        return;
    }
    [...frames].sort((a, b) => Number(a.sequence) - Number(b.sequence)).forEach((frame) => {
        const row = document.createElement('tr');
        for (const value of [frame.sequence, frame.frameId]) {
            const cell = document.createElement('td');
            cell.textContent = value === undefined || value === null ? '—' : String(value);
            row.appendChild(cell);
        }
        const statusCell = document.createElement('td');
        statusCell.textContent = frame.status === undefined || frame.status === null
            ? '—'
            : String(frame.status);
        const stage = typeof frame.stage === 'string' && frame.stage.trim()
            ? frame.stage
            : 'niepodany';
        const message = typeof frame.message === 'string' && frame.message.trim()
            ? frame.message
            : 'brak komunikatu';
        const stageLine = document.createElement('div');
        stageLine.textContent = `Etap: ${stage}`;
        const messageLine = document.createElement('div');
        messageLine.textContent = `Komunikat: ${message}`;
        statusCell.append(stageLine, messageLine);
        row.appendChild(statusCell);
        const progressCell = document.createElement('td');
        const amount = Math.max(0, Math.min(100, Number(frame.progress) || 0));
        progressCell.textContent = `${amount}%`;
        row.appendChild(progressCell);
        const errorCell = document.createElement('td');
        errorCell.textContent = typeof frame.error === 'string' && frame.error
            ? 'Przetwarzanie nie powiodło się; utwórz nową sesję. Szczegóły techniczne ukryto.'
            : '—';
        row.appendChild(errorCell);
        el.serverFrames.appendChild(row);
    });
}

function setSession(sessionId, payload = null) {
    const changedSession = activeSessionId !== sessionId;
    if (changedSession) {
        previewLoadToken += 1;
        viewer.cancelPendingLoad();
        el.modelViewer.setAttribute('aria-busy', 'false');
    }
    activeSessionId = sessionId;
    activeSession = payload;
    if (!queuesBySession.has(sessionId)) queuesBySession.set(sessionId, []);
    if (payload && payload.frames) statusBySession.set(sessionId, payload);
    if (loadedModel.sessionId !== sessionId) {
        viewer.dispose();
        el.modelViewer.replaceChildren();
        loadedModel.sessionId = null;
        loadedModel.version = 0;
        failedModelKey.sessionId = null;
        failedModelKey.version = 0;
        el.modelMessage.textContent = 'Sprawdzam dostępność modelu dla tej sesji…';
    }
    el.openSessionId.value = sessionId;
    renderSessionControls();
    renderServerFrames(statusBySession.get(sessionId)?.frames || []);
    if (payload) applyStatus(payload);
}

function applyStatus(payload) {
    if (!payload || payload.systemSessionId !== activeSessionId) return;
    activeSession = payload;
    statusBySession.set(activeSessionId, payload);
    const serverFrames = Array.isArray(payload.frames) ? payload.frames : [];
    for (const item of queueFor()) {
        let frameId = item.snapshot?.metadata.frameId;
        if (!frameId) {
            try { frameId = parseMetadata(item.metadataText).frameId; } catch (error) { frameId = null; }
        }
        const serverFrame = frameId ? serverFrames.find((frame) => frame.frameId === frameId) : null;
        if (serverFrame && item.state !== 'uploading' && item.state !== 'validating') {
            item.state = serverFrame.status || 'queued';
            item.uploadProgress = Math.max(0, Math.min(100, Number(serverFrame.progress) || 0));
            item.statusMessage = `Serwer: ${serverFrame.status || 'unknown'} · postęp przetwarzania ${item.uploadProgress}%.`;
            item.error = typeof serverFrame.error === 'string' && serverFrame.error
                ? 'Przetwarzanie nie powiodło się. Szczegóły techniczne ukryto.'
                : '';
        }
    }
    renderSessionControls();
    renderServerFrames(payload.frames || []);
    const version = Number(payload.session?.currentVersion) || 0;
    el.downloadModel.hidden = version < 1;
    if (version > 0) {
        el.downloadModel.href = `${API}model.php?systemSessionId=${encodeURIComponent(activeSessionId)}&version=${encodeURIComponent(version)}`;
        el.downloadModel.download = `model.v${version}.glb`;
        el.modelMessage.textContent = `Dostępna jest opublikowana wersja v${version}.`;
    } else {
        el.downloadModel.removeAttribute('href');
        el.modelMessage.textContent = 'Brak opublikowanego modelu (currentVersion = 0).';
    }
    maybeLoadLatestModel(version);
}

async function pollStatus() {
    if (!activeSessionId || polling || switchingSession) return;
    const requestedId = activeSessionId;
    polling = true;
    try {
        const payload = await requestJson(`${API}sessions.php?systemSessionId=${encodeURIComponent(requestedId)}`);
        if (activeSessionId === requestedId) {
            applyStatus(payload);
            clearError();
        }
    } catch (error) {
        if (activeSessionId === requestedId) showError(error.message);
    } finally {
        polling = false;
    }
}

async function createOrResumeSession() {
    clearError();
    const deviceId = el.deviceId.value.trim();
    if (!deviceId || new TextEncoder().encode(deviceId).byteLength > 128) {
        showError('deviceId musi zawierać od 1 do 128 bajtów.');
        el.deviceId.focus();
        return;
    }
    localStorage.setItem('img3d_multiphoto_device_id', deviceId);
    el.createSession.disabled = true;
    try {
        const payload = await requestJson(`${API}sessions.php`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ deviceId })
        });
        setSession(payload.systemSessionId, {
            systemSessionId: payload.systemSessionId,
            session: { status: payload.status, currentVersion: 0, acceptingFrames: true },
            frames: []
        });
        el.connectionState.textContent = payload.reused ? 'Wznowiono aktywną sesję' : 'Utworzono nową sesję';
        el.uploadMessage.textContent = payload.reused
            ? 'API wznowiło sesję przypisaną do tego deviceId.'
            : 'Utworzono nową sesję systemową.';
        await pollStatus();
    } catch (error) {
        showError(error.message);
    } finally {
        el.createSession.disabled = false;
    }
}

async function openExistingSession() {
    clearError();
    const sessionId = el.openSessionId.value.trim();
    if (!/^[a-f0-9]{32}$/.test(sessionId)) {
        showError('systemSessionId musi zawierać 32 małe znaki hex.');
        el.openSessionId.focus();
        return;
    }
    el.openSession.disabled = true;
    switchingSession = true;
    try {
        const payload = await requestJson(`${API}sessions.php?systemSessionId=${encodeURIComponent(sessionId)}`);
        setSession(sessionId, payload);
        clearError();
    } catch (error) {
        showError(error.message);
    } finally {
        switchingSession = false;
        el.openSession.disabled = false;
    }
}

function updateUploadProgress(item, percent) {
    item.uploadProgress = percent;
    const cards = [...el.frameQueue.querySelectorAll('.frame-card')];
    const index = queueFor().indexOf(item);
    const card = cards[index];
    if (!card) return;
    const bar = card.querySelector('.frame-progress span');
    const progress = card.querySelector('.frame-progress');
    const bounded = Math.max(0, Math.min(100, percent));
    if (bar) bar.style.width = `${bounded}%`;
    if (progress) progress.setAttribute('aria-valuenow', String(bounded));
    const status = card.querySelector('.frame-content > .subtle');
    if (status) status.textContent = `Wysyłanie obrazu: ${bounded}%`;
}

function uploadWithProgress(item, snapshot) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const url = `${API}frames.php?systemSessionId=${encodeURIComponent(snapshot.sessionId)}`;
        xhr.open('POST', url);
        xhr.timeout = 180000;
        xhr.upload.addEventListener('progress', (event) => {
            if (event.lengthComputable) {
                updateUploadProgress(item, Math.floor((event.loaded / event.total) * 100));
            }
        });
        xhr.addEventListener('error', () => reject(new Error('Błąd sieci podczas wysyłania. Ta sama klatka może zostać bezpiecznie ponowiona.')));
        xhr.addEventListener('timeout', () => reject(new Error('Przekroczono czas uploadu. Ponowienie użyje tych samych bajtów i metadanych.')));
        xhr.addEventListener('load', () => {
            let payload = null;
            try { payload = JSON.parse(xhr.responseText); } catch (error) {}
            if (xhr.status < 200 || xhr.status >= 300 || !payload || payload.success !== true) {
                reject(new Error(apiError({ status: xhr.status }, payload)));
                return;
            }
            if (payload.systemSessionId !== snapshot.sessionId || payload.frameId !== snapshot.metadata.frameId) {
                reject(new Error('Odpowiedź API nie odpowiada wysłanej sesji lub frameId.'));
                return;
            }
            resolve(payload);
        });
        const formData = new FormData();
        formData.append('photo', snapshot.file, snapshot.file.name);
        formData.append('metadata', snapshot.metadataText);
        xhr.send(formData);
    });
}

async function uploadFrame(item) {
    clearError();
    if (!activeSessionId || item.sessionId !== activeSessionId) {
        showError('Ta klatka należy do innej systemSessionId. Otwórz przypisaną sesję przed wysyłaniem.');
        return false;
    }
    if (!canAcceptFrames()) {
        showError('Ta sesja jest zamknięta lub nie przyjmuje klatek.');
        return false;
    }
    const queue = queueFor();
    try {
        if (!item.snapshot) {
            item.state = 'validating';
            item.statusMessage = 'Sprawdzanie oryginalnego pliku i metadanych…';
            renderQueue();
            const metadata = await validateFrame(item, queue);
            if (activeSessionId !== item.sessionId) {
                throw new Error('Zmieniono aktywną sesję podczas walidacji. Otwórz właściwą sesję i ponów.');
            }
            item.snapshot = Object.freeze({
                file: item.file,
                metadataText: item.metadataText,
                metadata,
                frameId: metadata.frameId,
                sha256: metadata.sha256,
                sessionId: item.sessionId
            });
        }
        item.state = 'uploading';
        item.error = '';
        item.uploadProgress = 0;
        item.statusMessage = `Przygotowano frameId=${item.snapshot.frameId}; wysyłanie oryginalnych bajtów…`;
        renderQueue();
        el.uploadMessage.textContent = `Wysyłanie ${item.file.name}…`;
        const payload = await uploadWithProgress(item, item.snapshot);
        item.state = 'queued';
        item.uploadProgress = 100;
        item.statusMessage = payload.idempotent
            ? `Serwer rozpoznał identyczne frameId=${payload.frameId}; status: ${payload.status}.`
            : `Przyjęto frameId=${payload.frameId}; status: ${payload.status}.`;
        item.error = '';
        renderQueue();
        el.uploadMessage.textContent = 'Upload przyjęty; postęp przetwarzania jest pobierany z API.';
        if (activeSessionId === item.snapshot.sessionId) await pollStatus();
        return true;
    } catch (error) {
        item.state = 'error';
        item.statusMessage = item.snapshot
            ? `Klatka zachowana do retry z tym samym frameId=${item.snapshot.frameId} i SHA-256.`
            : 'Walidacja nie powiodła się. Popraw JSON lub usuń klatkę i dodaj ponownie.';
        item.error = error.message;
        renderQueue();
        el.uploadMessage.textContent = 'Wystąpił błąd klatki.';
        return false;
    }
}

async function uploadAll() {
    if (batchRunning) return;
    const queue = queueFor();
    const pending = queue.filter((item) => item.state !== 'uploading' && item.state !== 'validating'
        && (!item.snapshot || item.state === 'error' || item.state === 'failed'));
    if (!pending.length) {
        el.uploadMessage.textContent = 'Brak nowych lub nieudanych klatek do wysłania.';
        return;
    }
    batchRunning = true;
    renderQueue();
    try {
        for (const item of pending) {
            await uploadFrame(item);
        }
    } finally {
        batchRunning = false;
        renderQueue();
    }
}

async function completeSession() {
    if (!activeSessionId || !canAcceptFrames()) return;
    const confirmed = window.confirm('Zamknąć przyjmowanie nowych klatek dla tej sesji? Klatki już w kolejce będą nadal przetwarzane.');
    if (!confirmed) return;
    el.completeSession.disabled = true;
    clearError();
    try {
        await requestJson(`${API}complete.php`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ systemSessionId: activeSessionId })
        });
        el.uploadMessage.textContent = 'Sesja zamknięta. Oczekujące klatki nadal mogą być przetwarzane.';
        await pollStatus();
    } catch (error) {
        showError(error.message);
    } finally {
        renderSessionControls();
    }
}

async function maybeLoadLatestModel(version, force = false) {
    if (!activeSessionId || version < 1) {
        el.retryModel.hidden = true;
        return;
    }
    const sessionId = activeSessionId;
    if (!force && loadedModel.sessionId === sessionId && loadedModel.version === version) return;
    if (!force && failedModelKey.sessionId === sessionId && failedModelKey.version === version) return;
    if (el.modelViewer.getAttribute('aria-busy') === 'true') return;

    const requestToken = ++previewLoadToken;
    el.modelViewer.setAttribute('aria-busy', 'true');
    el.retryModel.hidden = true;
    el.modelMessage.textContent = `Pobieranie podglądu niezmiennej wersji v${version}…`;
    const url = `${API}model.php?systemSessionId=${encodeURIComponent(sessionId)}&version=${encodeURIComponent(version)}`;
    try {
        const succeeded = await viewer.loadUrl(url);
        if (!succeeded) throw new Error(`Nie można pobrać wersji v${version}.`);
        if (requestToken !== previewLoadToken || activeSessionId !== sessionId) return;
        loadedModel.sessionId = sessionId;
        loadedModel.version = version;
        failedModelKey.sessionId = null;
        failedModelKey.version = 0;
        el.modelMessage.textContent = `Podgląd pokazuje opublikowaną wersję v${version}.`;
    } catch (error) {
        if (requestToken !== previewLoadToken || activeSessionId !== sessionId) return;
        failedModelKey.sessionId = sessionId;
        failedModelKey.version = version;
        el.modelMessage.textContent = `Wersja v${version} jest wskazana przez status, ale nie można pobrać modelu. Sprawdź później lub ponów pobranie.`;
        el.retryModel.hidden = false;
    } finally {
        if (requestToken === previewLoadToken) el.modelViewer.setAttribute('aria-busy', 'false');
    }
}

function addImages(fileList) {
    if (!activeSessionId || !canAcceptFrames()) {
        showError('Najpierw utwórz/wznów otwartą sesję systemową.');
        return;
    }
    const queue = queueFor();
    const files = Array.from(fileList || []);
    if (queue.length + files.length > 500) {
        showError('Limit API to 500 klatek w sesji.');
        return;
    }
    files.forEach((file) => {
        queue.push({
            file,
            sessionId: activeSessionId,
            previewUrl: URL.createObjectURL(file),
            metadataText: '',
            snapshot: null,
            state: 'ready',
            statusMessage: '',
            uploadProgress: 0,
            error: ''
        });
    });
    el.imageFiles.value = '';
    clearError();
    renderQueue();
}

el.deviceId.value = localStorage.getItem('img3d_multiphoto_device_id') || randomDeviceId();
el.createSession.addEventListener('click', createOrResumeSession);
el.openSession.addEventListener('click', openExistingSession);
el.openSessionId.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') openExistingSession();
});
el.deviceId.addEventListener('change', () => {
    localStorage.setItem('img3d_multiphoto_device_id', el.deviceId.value.trim());
});
el.imageFiles.addEventListener('change', () => addImages(el.imageFiles.files));
el.uploadAll.addEventListener('click', uploadAll);
el.refreshStatus.addEventListener('click', pollStatus);
el.completeSession.addEventListener('click', completeSession);
el.retryModel.addEventListener('click', () => {
    failedModelKey.sessionId = null;
    failedModelKey.version = 0;
    const version = Number(activeSession?.session?.currentVersion) || 0;
    maybeLoadLatestModel(version, true);
});

if (!window.isSecureContext && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
    showError('Web Crypto wymaga bezpiecznego kontekstu HTTPS lub localhost. Metadane SHA-256 nie będą generowane automatycznie.');
}
setInterval(pollStatus, 3000);
renderSessionControls();

window.addEventListener('beforeunload', () => {
    viewer.dispose();
    for (const queue of queuesBySession.values()) {
        queue.forEach((item) => URL.revokeObjectURL(item.previewUrl));
    }
});
