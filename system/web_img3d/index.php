<?php

require_once __DIR__ . '/cleanup.php';

$dataDir = __DIR__ . '/data';
$maxSessionsPerMinute = 30;

/*
|--------------------------------------------------------------------------
| Rate limit
|--------------------------------------------------------------------------
*/

$clientIp = $_SERVER['REMOTE_ADDR'] ?? 'unknown';
$rateLimitFile = $dataDir . '/.rate_limit.json';

$now = time();
$rateLimitData = [];

if (file_exists($rateLimitFile)) {
    $json = file_get_contents($rateLimitFile);

    if ($json !== false) {
        $decoded = json_decode($json, true);

        if (is_array($decoded)) {
            $rateLimitData = $decoded;
        }
    }
}

if (!isset($rateLimitData[$clientIp]) || !is_array($rateLimitData[$clientIp])) {
    $rateLimitData[$clientIp] = [];
}

/*
 * Usuń wpisy starsze niż 60 sekund.
 */
$rateLimitData[$clientIp] = array_values(
    array_filter(
        $rateLimitData[$clientIp],
        static function ($timestamp) use ($now) {
            return is_numeric($timestamp)
                && ((int) $timestamp > $now - 60);
        }
    )
);

if (count($rateLimitData[$clientIp]) >= $maxSessionsPerMinute) {
    $oldest = min($rateLimitData[$clientIp]);
    $retryAfter = max(1, 60 - ($now - $oldest));

    http_response_code(429);
    header('Content-Type: text/html; charset=utf-8');

    echo '<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <title>Za dużo sesji</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 700px;
            margin: 60px auto;
            padding: 20px;
        }

        .error {
            padding: 20px;
            background: #fee;
            border: 1px solid #d88;
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <div class="error">
        <h2>Za dużo żądań</h2>
        <p>
            Możesz utworzyć maksymalnie
            <strong>' . $maxSessionsPerMinute . '</strong>
            sesje w ciągu minuty.
        </p>
        <p>
            Spróbuj ponownie za około
            <strong>' . $retryAfter . ' s</strong>.
        </p>
    </div>
</body>
</html>';

    exit;
}

/*
 * Zapisz utworzenie nowej sesji.
 */
$rateLimitData[$clientIp][] = $now;

file_put_contents(
    $rateLimitFile,
    json_encode(
        $rateLimitData,
        JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE
    ),
    LOCK_EX
);

/*
|--------------------------------------------------------------------------
| Utworzenie sesji
|--------------------------------------------------------------------------
*/

$sessionId = bin2hex(random_bytes(16));
$createdOn = (int) round(microtime(true) * 1000);

$sessionDir = $dataDir . '/' . $sessionId;

if (!mkdir($sessionDir, 0755, true)) {
    http_response_code(500);
    exit('Nie udało się utworzyć katalogu sesji.');
}

/*
 * Początkowy stan sesji.
 */
$state = [
    'createdOn' => $createdOn,
    'status' => 'oczekiwanie',
    'progress' => 0
];

file_put_contents(
    $sessionDir . '/state.json',
    json_encode(
        $state,
        JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE
    ),
    LOCK_EX
);

?>
<!DOCTYPE html>
<html lang="pl">

<head>
    <meta charset="UTF-8">

    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Image → 3D</title>

    <!--
        Three.js
    -->
    <script type="importmap">
    {
        "imports": {
            "three": "https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js",
            "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.180.0/examples/jsm/"
        }
    }
    </script>

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            font-family: Arial, sans-serif;
            margin: 0;
            background: #f5f5f5;
            color: #222;
        }

        .container {
            max-width: 1900px;
            margin: 40px auto;
            padding: 25px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
        }

        h1 {
            margin-top: 0;
        }

        .session-info {
            display: none;
            padding: 15px;
            background: #f0f0f0;
            border-radius: 8px;
            margin-bottom: 25px;
        }

        .session-info div {
            margin: 5px 0;
        }

        .label {
            font-weight: bold;
        }

        .upload-section {
            margin: 25px 0;
        }

        #photoInput {
            display: none;
        }

        .button {
            display: inline-block;
            border: 0;
            border-radius: 7px;
            padding: 12px 20px;
            font-size: 16px;
            cursor: pointer;
            background: #1976d2;
            color: white;
        }

        .button:hover {
            background: #1565c0;
        }

        .button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .new-session {
            display: none;
            background: #555;
            margin-left: 10px;
        }

        .new-session:hover {
            background: #444;
        }

        .status {
            display: none;
            margin-top: 20px;
            padding: 15px;
            border-radius: 8px;
            background: #f0f0f0;
        }

        .progress-container {
            margin-top: 10px;
            height: 20px;
            background: #ddd;
            border-radius: 10px;
            overflow: hidden;
        }

        .progress-bar {
            height: 100%;
            width: 0%;
            background: #1976d2;
            transition: width 0.3s ease;
        }

        .error {
            margin-top: 15px;
            padding: 12px;
            background: #fee;
            border: 1px solid #d88;
            color: #900;
            border-radius: 7px;
            display: none;
        }

        /*
         * Viewer 3D
         */
        #viewer {
            position: relative;
            margin-top: 30px;
            width: 100%;
            height: 600px;
            border-radius: 8px;
            background: #eee;
            overflow: hidden;
            color: #777;
        }

        #viewer canvas {
            display: block;
            width: 100%;
            height: 100%;
        }

        .viewer-message {
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #777;
            pointer-events: none;
        }

        .filename {
            display: none;
            margin-top: 10px;
            color: #555;
            font-size: 14px;
        }
    </style>

</head>

<body>

    <div class="container">

        <h1>Image → 3D</h1>
        <p>System przeznaczony do generowania modelu 3D dla elementów architektury z pojedyńczego zdjęcia.</p>
        <p>Jego celem jest wyszukanie dominujących płaszczyzn z pominięciem nieregularnych obiektów i stworzenie lekkiego modelu geometrycznego na podstawie odnalezionych płaszczyzn.</p>

        <div class="session-info">

            <div>
                <span class="label">Session ID:</span>
                <span id="sessionId"></span>
            </div>

            <div>
                <span class="label">Utworzono:</span>
                <span id="createdOn"></span>
            </div>

        </div>

        <div class="upload-section">

            <label for="photoInput" class="button" id="uploadButton">
                Wczytaj zdjęcie z urządzenia
            </label>

            <input type="file" id="photoInput" accept="image/jpeg,image/png,image/webp">

            <button type="button" class="button new-session" id="newSessionButton">
                Nowa sesja
            </button>

            <div class="filename" id="filename"></div>

        </div>

        <div class="status" id="status-container">

            <div>
                <strong>Status:</strong>
                <span id="statusText">oczekiwanie</span>
            </div>

            <div class="progress-container">

                <div class="progress-bar" id="progressBar"></div>

            </div>

            <div style="margin-top: 8px;">

                <span id="progressText">0%</span>

            </div>

        </div>

        <div class="error" id="errorBox"></div>

        <div id="viewer">

            <div class="viewer-message">
                Podgląd modelu 3D pojawi się tutaj.
            </div>

        </div>

    </div>


    <script type="module">

        import * as THREE from 'three';

        import {
            GLTFLoader
        } from 'three/addons/loaders/GLTFLoader.js';

        import {
            OrbitControls
        } from 'three/addons/controls/OrbitControls.js';


        /*
        |--------------------------------------------------------------------------
        | Dane sesji
        |--------------------------------------------------------------------------
        */

        const sessionId =
            <?= json_encode($sessionId) ?>;

        const createdOn =
            <?= json_encode($createdOn) ?>;


        /*
        |--------------------------------------------------------------------------
        | Elementy DOM
        |--------------------------------------------------------------------------
        */

        const photoInput =
            document.getElementById('photoInput');

        const uploadButton =
            document.getElementById('uploadButton');

        const newSessionButton =
            document.getElementById('newSessionButton');

        const sessionIdElement =
            document.getElementById('sessionId');

        const createdOnElement =
            document.getElementById('createdOn');

        const filenameElement =
            document.getElementById('filename');

        const statusText =
            document.getElementById('statusText');

        const progressText =
            document.getElementById('progressText');

        const progressBar =
            document.getElementById('progressBar');

        const errorBox =
            document.getElementById('errorBox');

        const viewer =
            document.getElementById('viewer');


        /*
        |--------------------------------------------------------------------------
        | Three.js
        |--------------------------------------------------------------------------
        */

        let scene = null;
        let camera = null;
        let renderer = null;
        let controls = null;
        let model = null;
        let animationFrame = null;


        /*
        |--------------------------------------------------------------------------
        | Informacje o sesji
        |--------------------------------------------------------------------------
        */

        sessionIdElement.textContent =
            sessionId;

        const createdDate =
            new Date(createdOn);

        createdOnElement.textContent =
            createdDate.toLocaleString('pl-PL');


        /*
         * Zapisz dane sesji.
         */

        sessionStorage.setItem(
            'img3d_session',
            JSON.stringify({
                sessionId: sessionId,
                createdOn: createdOn
            })
        );


        console.log(
            'Image 3D session:',
            {
                sessionId: sessionId,
                createdOn: createdOn,
                createdDate:
                    createdDate.toLocaleString('pl-PL')
            }
        );


        /*
        |--------------------------------------------------------------------------
        | Pomocnicze funkcje
        |--------------------------------------------------------------------------
        */

        function showError(message) {

            errorBox.textContent =
                message;

            errorBox.style.display =
                'block';
        }


        function clearError() {

            errorBox.textContent =
                '';

            errorBox.style.display =
                'none';
        }


        function setStatus(status, progress) {

            statusText.textContent =
                status;

            progress =
                Number(progress) || 0;

            progress =
                Math.max(
                    0,
                    Math.min(
                        100,
                        progress
                    )
                );

            progressBar.style.width =
                progress + '%';

            progressText.textContent =
                progress + '%';
        }


        /*
        |--------------------------------------------------------------------------
        | Viewer
        |--------------------------------------------------------------------------
        */

        function initViewer() {

            /*
             * Jeżeli viewer już istnieje,
             * wyczyść poprzedni model.
             */

            if (animationFrame) {

                cancelAnimationFrame(
                    animationFrame
                );

                animationFrame = null;
            }


            if (renderer) {

                renderer.dispose();

                renderer = null;
            }


            viewer.innerHTML = '';


            /*
             * Scena
             */

            scene =
                new THREE.Scene();

            scene.background =
                new THREE.Color(0xeeeeee);


            /*
             * Kamera
             */

            const width =
                viewer.clientWidth;

            const height =
                viewer.clientHeight;

            camera =
                new THREE.PerspectiveCamera(
                    45,
                    width / height,
                    0.01,
                    10000
                );


            /*
             * Renderer
             */

            renderer =
                new THREE.WebGLRenderer({
                    antialias: true
                });

            renderer.setPixelRatio(
                window.devicePixelRatio
            );

            renderer.setSize(
                width,
                height
            );

            renderer.outputColorSpace =
                THREE.SRGBColorSpace;

            viewer.appendChild(
                renderer.domElement
            );


            /*
             * Sterowanie kamerą
             */

            controls =
                new OrbitControls(
                    camera,
                    renderer.domElement
                );

            controls.enableDamping =
                true;

            controls.dampingFactor =
                0.05;

            controls.screenSpacePanning =
                true;

            controls.minDistance =
                0.01;

            controls.maxDistance =
                10000;


            /*
             * Światło otoczenia
             */

            const ambientLight =
                new THREE.AmbientLight(
                    0xffffff,
                    2
                );

            scene.add(
                ambientLight
            );


            /*
             * Główne światło
             */

            const directionalLight =
                new THREE.DirectionalLight(
                    0xffffff,
                    3
                );

            directionalLight.position.set(
                5,
                10,
                5
            );

            scene.add(
                directionalLight
            );


            /*
             * Drugie światło
             */

            const directionalLight2 =
                new THREE.DirectionalLight(
                    0xffffff,
                    1
                );

            directionalLight2.position.set(
                -5,
                5,
                -5
            );

            scene.add(
                directionalLight2
            );


            /*
             * Renderowanie
             */

            function animate() {

                animationFrame =
                    requestAnimationFrame(
                        animate
                    );

                controls.update();

                renderer.render(
                    scene,
                    camera
                );
            }

            animate();


            /*
             * Obsługa zmiany rozmiaru.
             */

            window.addEventListener(
                'resize',
                resizeViewer
            );
        }


        function resizeViewer() {

            if (
                !renderer ||
                !camera
            ) {
                return;
            }

            const width =
                viewer.clientWidth;

            const height =
                viewer.clientHeight;

            if (
                width <= 0 ||
                height <= 0
            ) {
                return;
            }

            camera.aspect =
                width / height;

            camera.updateProjectionMatrix();

            renderer.setSize(
                width,
                height
            );
        }


        /*
        |--------------------------------------------------------------------------
        | Dopasowanie kamery do modelu
        |--------------------------------------------------------------------------
        */

        function fitCameraToModel(model) {

            const box =
                new THREE.Box3()
                    .setFromObject(model);

            const size =
                box.getSize(
                    new THREE.Vector3()
                );

            const center =
                box.getCenter(
                    new THREE.Vector3()
                );


            /*
             * Przenieś model tak,
             * aby jego środek znajdował się
             * w środku sceny.
             */

            model.position.x -=
                center.x;

            model.position.y -=
                center.y;

            model.position.z -=
                center.z;


            const maxSize =
                Math.max(
                    size.x,
                    size.y,
                    size.z
                );


            /*
             * Zabezpieczenie przed
             * nieprawidłowym rozmiarem.
             */

            if (
                !Number.isFinite(maxSize) ||
                maxSize <= 0
            ) {
                console.warn(
                    'Nieprawidłowy rozmiar modelu.'
                );

                camera.position.set(
                    0,
                    0,
                    5
                );

                camera.lookAt(
                    0,
                    0,
                    0
                );

                return;
            }


            /*
             * Odległość kamery wynikająca
             * z pola widzenia.
             */

            const fov =
                THREE.MathUtils.degToRad(
                    camera.fov
                );

            const distance =
                maxSize /
                (2 * Math.tan(fov / 2));


            camera.position.set(
                distance * 0.8,
                distance * 0.5,
                distance * 1.5
            );


            camera.near =
                Math.max(
                    maxSize / 10000,
                    0.001
                );

            camera.far =
                Math.max(
                    maxSize * 100,
                    100
                );

            camera.updateProjectionMatrix();


            controls.target.set(
                0,
                0,
                0
            );

            controls.update();
        }


        /*
        |--------------------------------------------------------------------------
        | Ładowanie GLB
        |--------------------------------------------------------------------------
        */

        async function loadGlb(glbUrl) {

            console.log(
                'Model GLB gotowy:',
                glbUrl
            );


            try {

                /*
                 * Pobierz plik z PHP.
                 */

                const response =
                    await fetch(
                        'get-glb.php?sessionId=' +
                        encodeURIComponent(
                            sessionId
                        ),
                        {
                            method: 'GET',
                            cache: 'no-store'
                        }
                    );


                if (!response.ok) {

                    throw new Error(
                        `HTTP ${response.status}`
                    );
                }


                /*
                 * GLB jako binarny ArrayBuffer.
                 */

                const glbData =
                    await response.arrayBuffer();


                console.log(
                    'GLB pobrany:',
                    glbData.byteLength,
                    'bajtów'
                );


                /*
                 * Utwórz viewer.
                 */

                initViewer();


                /*
                 * Załaduj GLB.
                 */

                const loader =
                    new GLTFLoader();


                loader.parse(
                    glbData,
                    '',
                    function (gltf) {

                        console.log(
                            'GLB załadowany:',
                            gltf
                        );


                        model =
                            gltf.scene;


                        scene.add(
                            model
                        );


                        /*
                         * Dopasuj kamerę.
                         */

                        fitCameraToModel(
                            model
                        );


                        console.log(
                            'Model wyświetlony.'
                        );
                    },
                    function (error) {

                        console.error(
                            'Błąd GLTFLoader:',
                            error
                        );

                        showError(
                            'Nie udało się odczytać modelu GLB.'
                        );
                    }
                );


            } catch (error) {

                console.error(
                    'Błąd pobierania GLB:',
                    error
                );

                showError(
                    'Nie udało się pobrać modelu GLB.'
                );
            }
        }


        /*
        |--------------------------------------------------------------------------
        | Upload zdjęcia
        |--------------------------------------------------------------------------
        */

        function loadImage(file) {

            return new Promise(
                function (resolve, reject) {

                    const image =
                        new Image();

                    const url =
                        URL.createObjectURL(file);

                    image.onload = function () {

                        URL.revokeObjectURL(url);

                        resolve(image);
                    };

                    image.onerror = function () {

                        URL.revokeObjectURL(url);

                        reject(
                            new Error(
                                'Nie udało się odczytać obrazu.'
                            )
                        );
                    };

                    image.src = url;
                }
            );
        }

        photoInput.addEventListener(
            'change',
            async function () {

                clearError();

                const file = photoInput.files[0];

                if (!file) {
                    return;
                }

                filenameElement.textContent =
                    'Wybrano: ' + file.name;

                /*
                 * Dozwolone typy.
                 */
                const allowedTypes = [
                    'image/jpeg',
                    'image/png',
                    'image/webp'
                ];

                if (!allowedTypes.includes(file.type)) {

                    showError(
                        'Nieprawidłowy typ pliku. ' +
                        'Wybierz JPG, PNG lub WEBP.'
                    );

                    photoInput.value = '';
                    filenameElement.textContent = '';

                    return;
                }

                /*
                 * Maksymalny rozmiar oryginalnego pliku:
                 * 20 MB.
                 */
                const maxSize =
                    20 * 1024 * 1024;

                if (file.size > maxSize) {

                    showError(
                        'Plik jest za duży. ' +
                        'Maksymalny rozmiar to 20 MB.'
                    );

                    photoInput.value = '';
                    filenameElement.textContent = '';

                    return;
                }

                /*
                 * Zablokuj upload podczas przetwarzania.
                 */
                uploadButton.style.pointerEvents = 'none';
                uploadButton.style.opacity = '0.5';

                newSessionButton.disabled = true;

                try {

                    /*
                     * Wczytaj obraz.
                     */
                    const image = await loadImage(file);

                    console.log(
                        'Oryginalny rozmiar:',
                        image.naturalWidth,
                        'x',
                        image.naturalHeight
                    );

                    /*
                     * Maksymalny rozmiar FHD.
                     */
                    const maxWidth = 1920;
                    const maxHeight = 1080;

                    let width = image.naturalWidth;
                    let height = image.naturalHeight;

                    /*
                     * Skalowanie tylko wtedy,
                     * gdy obraz przekracza FHD.
                     */
                    if (
                        width > maxWidth ||
                        height > maxHeight
                    ) {

                        const scale = Math.min(
                            maxWidth / width,
                            maxHeight / height
                        );

                        width = Math.round(
                            width * scale
                        );

                        height = Math.round(
                            height * scale
                        );
                    }

                    console.log(
                        'Rozmiar po skalowaniu:',
                        width,
                        'x',
                        height
                    );

                    /*
                     * Canvas.
                     */
                    const canvas =
                        document.createElement('canvas');

                    canvas.width = width;
                    canvas.height = height;

                    const context =
                        canvas.getContext('2d');

                    context.drawImage(
                        image,
                        0,
                        0,
                        width,
                        height
                    );

                    /*
                     * Zamień canvas na Blob JPEG.
                     *
                     * Jakość 0.90 daje zwykle dobry
                     * kompromis pomiędzy jakością
                     * i rozmiarem pliku.
                     */
                    const resizedBlob =
                        await new Promise(
                            function (resolve, reject) {

                                canvas.toBlob(
                                    function (blob) {

                                        if (!blob) {
                                            reject(
                                                new Error(
                                                    'Nie udało się przeskalować obrazu.'
                                                )
                                            );

                                            return;
                                        }

                                        resolve(blob);
                                    },
                                    'image/jpeg',
                                    0.90
                                );
                            }
                        );

                    console.log(
                        'Rozmiar przed wysłaniem:',
                        Math.round(
                            resizedBlob.size / 1024
                        ),
                        'KB'
                    );
                    document.querySelector('.status').style.display = 'block';
                    setStatus(
                        'wysyłanie',
                        0
                    );

                    /*
                     * Utwórz FormData.
                     */
                    const formData =
                        new FormData();

                    /*
                     * Zawsze wysyłamy JPEG.
                     */
                    formData.append(
                        'photo',
                        resizedBlob,
                        'photo.jpg'
                    );

                    /*
                     * Upload.
                     */
                    const response =
                        await fetch(
                            'upload.php?sessionId=' +
                            encodeURIComponent(
                                sessionId
                            ),
                            {
                                method: 'POST',
                                body: formData
                            }
                        );

                    const data =
                        await response.json();

                    if (
                        !response.ok ||
                        !data.success
                    ) {

                        throw new Error(
                            data.error ||
                            'Upload zdjęcia nie powiódł się.'
                        );
                    }

                    setStatus(
                        data.status ||
                        'uploading',
                        0
                    );

                    console.log(
                        'Zdjęcie zostało przesłane:',
                        data
                    );

                } catch (error) {

                    console.error(
                        error
                    );

                    showError(
                        error.message ||
                        'Wystąpił błąd podczas przetwarzania zdjęcia.'
                    );

                    setStatus(
                        'błąd',
                        0
                    );

                    uploadButton.style.pointerEvents = '';
                    uploadButton.style.opacity = '';

                    newSessionButton.disabled = false;
                }
            }
        );

        /*
        |--------------------------------------------------------------------------
        | Nowa sesja
        |--------------------------------------------------------------------------
        */

        newSessionButton.addEventListener(
            'click',
            function () {
                window.location.reload();
            }
        );


        /*
        |--------------------------------------------------------------------------
        | Polling statusu
        |--------------------------------------------------------------------------
        */

        let pollingTimer =
            null;


        async function checkStatus() {

            try {

                const response =
                    await fetch(
                        'status.php?sessionId=' +
                        encodeURIComponent(
                            sessionId
                        ),
                        {
                            cache: 'no-store'
                        }
                    );


                if (!response.ok) {

                    throw new Error(
                        'Nie udało się pobrać statusu sesji.'
                    );
                }


                const data =
                    await response.json();


                if (
                    data.status !== undefined
                ) {

                    statusText.textContent =
                        data.status;
                }


                if (
                    data.progress !== undefined
                ) {

                    const progress =
                        Number(
                            data.progress
                        ) || 0;


                    progressBar.style.width =
                        progress + '%';

                    progressText.textContent =
                        progress + '%';
                }


                /*
                 * Model gotowy.
                 */

                if (
                    data.status === 'ready'
                ) {

                    clearInterval(
                        pollingTimer
                    );


                    setStatus(
                        'gotowe',
                        100
                    );
                    document.querySelector('.status').style.display = 'none';

                    newSessionButton.disabled =
                        false;


                    if (data.glb) {

                        await loadGlb(
                            data.glb
                        );
                    }


                    return;
                }


                /*
                 * Błąd przetwarzania.
                 */

                if (
                    data.status === 'error'
                ) {

                    clearInterval(
                        pollingTimer
                    );


                    showError(
                        data.error ||
                        'Wystąpił błąd podczas przetwarzania modelu.'
                    );


                    newSessionButton.disabled =
                        false;
                }


            } catch (error) {

                console.error(
                    'Błąd podczas sprawdzania statusu:',
                    error
                );

            }
        }


        /*
        |--------------------------------------------------------------------------
        | Uruchom polling
        |--------------------------------------------------------------------------
        */

        pollingTimer =
            setInterval(
                checkStatus,
                3000
            );


        /*
         * Pierwsze sprawdzenie od razu.
         */

        checkStatus();

    </script>

</body>

</html>