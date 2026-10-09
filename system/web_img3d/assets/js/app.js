import { ModelViewer } from './viewer.js';

const configElement = document.getElementById('img3dConfig');
if (!configElement) {
    throw new Error('Missing application configuration.');
}

const { sessionId, createdOn, language, text, photoUrl } = JSON.parse(configElement.textContent);
const elements = {
    photoInput: document.getElementById('photoInput'),
    uploadButton: document.getElementById('uploadButton'),
    newSessionButton: document.getElementById('newSessionButton'),
    downloadModelButton: document.getElementById('downloadModelButton'),
    sessionId: document.getElementById('sessionId'),
    createdOn: document.getElementById('createdOn'),
    filename: document.getElementById('filename'),
    imagePreviewWrapper: document.getElementById('imagePreviewWrapper'),
    imagePreview: document.getElementById('imagePreview'),
    status: document.getElementById('status-container'),
    statusText: document.getElementById('statusText'),
    progressText: document.getElementById('progressText'),
    progressBar: document.getElementById('progressBar'),
    errorBox: document.getElementById('errorBox'),
    viewer: document.getElementById('viewer')
};

let previewUrl = null;
let pollingTimer = null;
let hasUploadedPhoto = false;
let uploadInProgress = false;
let photoCheckCompleted = false;
let currentStatus = 'waiting';

const modelViewer = new ModelViewer(elements.viewer, () => {
    showError(text.glb_download_error);
});

function translateStatus(status) {
    const statusKeys = {
        'oczekiwanie': 'waiting',
        waiting: 'waiting',
        'wysyłanie': 'uploading',
        uploading: 'uploading',
        uploaded: 'uploaded',
        processing: 'processing',
        'przetwarzanie': 'processing',
        ready: 'ready',
        'gotowe': 'ready',
        error: 'error',
        'błąd': 'error'
    };

    const key = statusKeys[status];
    return key ? text[key] : status;
}

function showError(message) {
    elements.errorBox.textContent = text.server_errors[message] || message;
    elements.errorBox.style.display = 'block';
}

function clearError() {
    elements.errorBox.textContent = '';
    elements.errorBox.style.display = 'none';
}

function setStatus(status, progress) {
    elements.statusText.textContent = translateStatus(status);
    const boundedProgress = Math.max(0, Math.min(100, Number(progress) || 0));
    elements.progressBar.style.width = `${boundedProgress}%`;
    elements.progressText.textContent = `${boundedProgress}%`;
    updateUploadButton(status);
}

function updateUploadButton(status) {
    const normalizedStatus = {
        'oczekiwanie': 'waiting',
        'wysyłanie': 'uploading',
        'przetwarzanie': 'processing',
        'gotowe': 'ready',
        'błąd': 'error'
    }[status] || status;
    const processing = ['uploading', 'uploaded', 'processing', 'ready', 'error']
        .includes(normalizedStatus);

    elements.uploadButton.hidden =
        !photoCheckCompleted || hasUploadedPhoto || uploadInProgress || processing;
}

function clearImagePreview() {
    if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = null;
    }

    elements.imagePreview.removeAttribute('src');
    elements.imagePreviewWrapper.style.display = 'none';
}

function loadImage(file) {
    return new Promise((resolve, reject) => {
        const image = new Image();
        const url = URL.createObjectURL(file);

        image.onload = () => {
            URL.revokeObjectURL(url);
            resolve(image);
        };

        image.onerror = () => {
            URL.revokeObjectURL(url);
            reject(new Error(text.image_read_error));
        };

        image.src = url;
    });
}

async function resizeImage(image) {
    const maxWidth = 1920;
    const maxHeight = 1080;
    const scale = Math.min(
        1,
        maxWidth / image.naturalWidth,
        maxHeight / image.naturalHeight
    );
    const width = Math.round(image.naturalWidth * scale);
    const height = Math.round(image.naturalHeight * scale);
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;

    const context = canvas.getContext('2d');
    if (!context) {
        throw new Error(text.image_resize_error);
    }

    context.drawImage(image, 0, 0, width, height);

    return new Promise((resolve, reject) => {
        canvas.toBlob((blob) => {
            if (blob) {
                resolve(blob);
            } else {
                reject(new Error(text.image_resize_error));
            }
        }, 'image/jpeg', 0.9);
    });
}

async function uploadPhoto(file) {
    const image = await loadImage(file);
    const resizedBlob = await resizeImage(image);
    const formData = new FormData();
    formData.append('photo', resizedBlob, 'photo.jpg');

    const response = await fetch(
        `upload.php?sessionId=${encodeURIComponent(sessionId)}`,
        { method: 'POST', body: formData }
    );
    const result = await response.json();

    if (!response.ok || !result.success) {
        throw new Error(result.error || text.upload_failed);
    }

    hasUploadedPhoto = true;
    setStatus(result.status || 'uploading', 0);
}

function resetFileInput() {
    elements.photoInput.value = '';
    elements.filename.textContent = '';
    elements.filename.style.display = 'none';
}

async function handleFileSelection() {
    clearError();

    const file = elements.photoInput.files?.[0];
    if (!file) {
        return;
    }

    elements.filename.textContent = `${text.selected_file} ${file.name}`;
    elements.filename.style.display = 'block';

    const allowedTypes = ['image/jpeg', 'image/png', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
        clearImagePreview();
        showError(text.invalid_image_type);
        resetFileInput();
        return;
    }

    if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
    }

    previewUrl = URL.createObjectURL(file);
    elements.imagePreview.src = previewUrl;
    elements.imagePreviewWrapper.style.display = 'block';

    if (file.size > 20 * 1024 * 1024) {
        clearImagePreview();
        showError(text.file_too_large);
        resetFileInput();
        return;
    }

    elements.uploadButton.style.pointerEvents = 'none';
    elements.uploadButton.style.opacity = '0.5';
    uploadInProgress = true;
    updateUploadButton('uploading');
    elements.newSessionButton.disabled = true;
    elements.status.style.display = 'block';
    setStatus('uploading', 0);

    try {
        await uploadPhoto(file);
    } catch (error) {
        uploadInProgress = false;
        console.error('Photo upload failed:', error);
        showError(error.message || text.image_processing_error);
        setStatus('error', 0);
        elements.uploadButton.style.pointerEvents = '';
        elements.uploadButton.style.opacity = '';
        elements.newSessionButton.disabled = false;
        elements.newSessionButton.style.display = 'inline-block';
        await checkStatus();
    }
}

async function checkStatus() {
    try {
        const response = await fetch(
            `status.php?sessionId=${encodeURIComponent(sessionId)}`,
            { cache: 'no-store' }
        );

        if (!response.ok) {
            throw new Error(text.session_status_error);
        }

        const data = await response.json();
        if (data.status !== undefined) {
            currentStatus = data.status;
            elements.statusText.textContent = translateStatus(currentStatus);
            updateUploadButton(currentStatus);
        }

        if (data.progress !== undefined) {
            const progress = Math.max(0, Math.min(100, Number(data.progress) || 0));
            elements.progressBar.style.width = `${progress}%`;
            elements.progressText.textContent = `${progress}%`;
        }

        if (data.status === 'ready') {
            clearInterval(pollingTimer);
            setStatus('ready', 100);
            elements.status.style.display = 'none';
            elements.newSessionButton.disabled = false;
            elements.newSessionButton.style.display = 'inline-block';

            if (data.glb) {
                elements.downloadModelButton.hidden = false;
                await modelViewer.load(sessionId);
            }
            return;
        }

        if (data.status === 'error') {
            clearInterval(pollingTimer);
            showError(data.error || text.model_processing_error);
            elements.newSessionButton.disabled = false;
            elements.newSessionButton.style.display = 'inline-block';
        }
    } catch (error) {
        console.error('Could not check session status:', error);
    }
}

function startNewSession() {
    const url = new URL(window.location.href);
    url.search = '';
    url.searchParams.set('lang', language);
    sessionStorage.removeItem('img3d_session');
    window.location.assign(url);
}

function downloadModel() {
    window.location.assign(
        `get-glb.php?sessionId=${encodeURIComponent(sessionId)}&download=1`
    );
}

async function restoreUploadedPhoto() {
    const response = await fetch(photoUrl, { cache: 'no-store' });

    if (response.status === 404) {
        photoCheckCompleted = true;
        updateUploadButton(currentStatus);
        return;
    }

    if (!response.ok) {
        throw new Error(text.photo_restore_error);
    }

    const photoBlob = await response.blob();
    hasUploadedPhoto = true;
    photoCheckCompleted = true;
    updateUploadButton('uploaded');
    previewUrl = URL.createObjectURL(photoBlob);
    elements.imagePreview.src = previewUrl;
    elements.imagePreviewWrapper.style.display = 'block';
    elements.filename.textContent = text.uploaded_photo;
    elements.filename.style.display = 'block';
}

function restoreSessionFromStorage() {
    if (new URLSearchParams(window.location.search).has('sessionId')) {
        return false;
    }

    const storedSession = sessionStorage.getItem('img3d_session');
    if (!storedSession) {
        return false;
    }

    let previousSession;
    try {
        previousSession = JSON.parse(storedSession);
    } catch (error) {
        sessionStorage.removeItem('img3d_session');
        console.warn('Ignoring invalid stored session data:', error);
        return false;
    }

    if (
        !previousSession
        || typeof previousSession.sessionId !== 'string'
        || !/^[a-f0-9]{32}$/.test(previousSession.sessionId)
    ) {
        sessionStorage.removeItem('img3d_session');
        return false;
    }

    const url = new URL(window.location.href);
    url.searchParams.set('lang', language);
    url.searchParams.set('sessionId', previousSession.sessionId);
    window.location.replace(url);
    return true;
}

function initializeSession() {
    elements.sessionId.textContent = sessionId;
    elements.createdOn.textContent = new Date(createdOn).toLocaleString(
        language === 'pl' ? 'pl-PL' : 'en-GB'
    );

    sessionStorage.setItem('img3d_session', JSON.stringify({ sessionId, createdOn }));
    const sessionUrl = new URL(window.location.href);
    sessionUrl.searchParams.set('lang', language);
    sessionUrl.searchParams.set('sessionId', sessionId);
    window.history.replaceState(null, '', sessionUrl);

    elements.photoInput.addEventListener('change', handleFileSelection);
    elements.newSessionButton.addEventListener('click', startNewSession);
    elements.downloadModelButton.addEventListener('click', downloadModel);

    restoreUploadedPhoto().catch((error) => {
        console.error('Could not restore uploaded photo:', error);
        showError(error.message || text.photo_restore_error);
    });

    pollingTimer = setInterval(checkStatus, 3000);
    checkStatus();
}

if (!restoreSessionFromStorage()) {
    initializeSession();
}

window.addEventListener('beforeunload', () => {
    clearInterval(pollingTimer);

    if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
    }

    modelViewer.dispose();
});
