<?php

require_once __DIR__ . '/cleanup.php';

$dataDir = __DIR__ . '/data';
$maxSessionsPerMinute = 3;

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
            return is_numeric($timestamp) && ((int) $timestamp > $now - 60);
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
    json_encode($rateLimitData, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE),
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
    json_encode($state, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE),
    LOCK_EX
);

?>
<!DOCTYPE html>
<html lang="pl">

<head>
    <meta charset="UTF-8">

    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Image → 3D</title>

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
            max-width: 900px;
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

        /*
         * Ukrywamy właściwy input file.
         * Użytkownik widzi tylko przycisk "Przekaż zdjęcie".
         */
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
            background: #555;
            margin-left: 10px;
        }

        .new-session:hover {
            background: #444;
        }

        .status {
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

        #viewer {
            margin-top: 30px;
            min-height: 400px;
            border-radius: 8px;
            background: #eee;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #777;
        }

        .filename {
            margin-top: 10px;
            color: #555;
            font-size: 14px;
        }
    </style>
</head>

<body>

    <div class="container">

        <h1>Image → 3D</h1>

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

            <!--
            Kliknięcie tego przycisku otwiera wybór pliku.
            Po wybraniu pliku upload rozpoczyna się automatycznie.
        -->
            <label for="photoInput" class="button" id="uploadButton">
                Przekaż zdjęcie
            </label>

            <input type="file" id="photoInput" accept="image/jpeg,image/png,image/webp">

            <button type="button" class="button new-session" id="newSessionButton">
                Nowa sesja
            </button>

            <div class="filename" id="filename"></div>

        </div>

        <div class="status">
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
            Podgląd modelu 3D pojawi się tutaj.
        </div>

    </div>

    <script>
        const sessionId = <?= json_encode($sessionId) ?>;
        const createdOn = <?= json_encode($createdOn) ?>;

        const photoInput = document.getElementById('photoInput');
        const uploadButton = document.getElementById('uploadButton');
        const newSessionButton = document.getElementById('newSessionButton');

        const sessionIdElement = document.getElementById('sessionId');
        const createdOnElement = document.getElementById('createdOn');

        const filenameElement = document.getElementById('filename');

        const statusText = document.getElementById('statusText');
        const progressText = document.getElementById('progressText');
        const progressBar = document.getElementById('progressBar');

        const errorBox = document.getElementById('errorBox');

        const viewer = document.getElementById('viewer');

        /*
        |--------------------------------------------------------------------------
        | Informacje o sesji
        |--------------------------------------------------------------------------
        */

        sessionIdElement.textContent = sessionId;

        const createdDate = new Date(createdOn);

        createdOnElement.textContent = createdDate.toLocaleString('pl-PL');

        /*
         * Zapisz dane sesji w sessionStorage.
         */
        sessionStorage.setItem(
            'img3d_session',
            JSON.stringify({
                sessionId: sessionId,
                createdOn: createdOn
            })
        );

        /*
         * Logowanie do konsoli.
         */
        console.log('Image 3D session:', {
            sessionId: sessionId,
            createdOn: createdOn,
            createdDate: createdDate.toLocaleString('pl-PL')
        });

        /*
        |--------------------------------------------------------------------------
        | Pomocnicze funkcje
        |--------------------------------------------------------------------------
        */

        function showError(message) {
            errorBox.textContent = message;
            errorBox.style.display = 'block';
        }

        function clearError() {
            errorBox.textContent = '';
            errorBox.style.display = 'none';
        }

        function setStatus(status, progress) {
            statusText.textContent = status;

            progress = Number(progress) || 0;

            progress = Math.max(0, Math.min(100, progress));

            progressBar.style.width = progress + '%';
            progressText.textContent = progress + '%';
        }

        /*
        |--------------------------------------------------------------------------
        | Automatyczny upload po wyborze zdjęcia
        |--------------------------------------------------------------------------
        */

        photoInput.addEventListener('change', async function () {

            clearError();

            const file = photoInput.files[0];

            if (!file) {
                return;
            }

            filenameElement.textContent =
                'Wybrano: ' + file.name;

            /*
             * Sprawdzenie typu po stronie klienta.
             * Ostateczna walidacja i tak odbywa się w upload.php.
             */
            const allowedTypes = [
                'image/jpeg',
                'image/png',
                'image/webp'
            ];

            if (!allowedTypes.includes(file.type)) {
                showError(
                    'Nieprawidłowy typ pliku. Wybierz JPG, PNG lub WEBP.'
                );

                photoInput.value = '';
                filenameElement.textContent = '';

                return;
            }

            /*
             * Maksymalnie 20 MB.
             */
            const maxSize = 20 * 1024 * 1024;

            if (file.size > maxSize) {
                showError(
                    'Plik jest za duży. Maksymalny rozmiar to 20 MB.'
                );

                photoInput.value = '';
                filenameElement.textContent = '';

                return;
            }

            /*
             * Zablokuj możliwość ponownego kliknięcia
             * podczas wysyłania.
             */
            uploadButton.style.pointerEvents = 'none';
            uploadButton.style.opacity = '0.5';

            newSessionButton.disabled = true;

            setStatus('wysyłanie', 0);

            const formData = new FormData();

            formData.append('photo', file);

            try {

                const response = await fetch(
                    'upload.php?sessionId=' +
                    encodeURIComponent(sessionId),
                    {
                        method: 'POST',
                        body: formData
                    }
                );

                const data = await response.json();

                if (!response.ok || !data.success) {
                    throw new Error(
                        data.error || 'Upload zdjęcia nie powiódł się.'
                    );
                }

                setStatus(
                    data.status || 'uploading',
                    0
                );

                console.log('Zdjęcie zostało przesłane:', data);

            } catch (error) {

                console.error(error);

                showError(
                    error.message ||
                    'Wystąpił błąd podczas wysyłania zdjęcia.'
                );

                setStatus('błąd', 0);

                uploadButton.style.pointerEvents = '';
                uploadButton.style.opacity = '';

                newSessionButton.disabled = false;
            }

        });

        /*
        |--------------------------------------------------------------------------
        | Nowa sesja
        |--------------------------------------------------------------------------
        */

        newSessionButton.addEventListener('click', function () {

            window.location.reload();

        });

        /*
        |--------------------------------------------------------------------------
        | Sprawdzanie statusu
        |--------------------------------------------------------------------------
        */

        let pollingTimer = null;

        async function checkStatus() {

            try {

                const response = await fetch(
                    'status.php?sessionId=' +
                    encodeURIComponent(sessionId),
                    {
                        cache: 'no-store'
                    }
                );

                if (!response.ok) {
                    throw new Error(
                        'Nie udało się pobrać statusu sesji.'
                    );
                }

                const data = await response.json();

                if (data.status !== undefined) {
                    statusText.textContent = data.status;
                }

                if (data.progress !== undefined) {
                    const progress = Number(data.progress) || 0;

                    progressBar.style.width = progress + '%';
                    progressText.textContent = progress + '%';
                }

                /*
                 * Model gotowy.
                 */
                if (data.status === 'ready') {

                    clearInterval(pollingTimer);

                    setStatus('gotowe', 100);

                    newSessionButton.disabled = false;

                    if (data.glb) {
                        loadGlb(data.glb);
                    }

                    return;
                }

                /*
                 * Błąd przetwarzania.
                 */
                if (data.status === 'error') {

                    clearInterval(pollingTimer);

                    showError(
                        data.error ||
                        'Wystąpił błąd podczas przetwarzania modelu.'
                    );

                    newSessionButton.disabled = false;

                }

            } catch (error) {

                console.error(
                    'Błąd podczas sprawdzania statusu:',
                    error
                );

            }

        }

        /*
         * Polling co 3 sekundy.
         */
        pollingTimer = setInterval(
            checkStatus,
            3000
        );

        /*
         * Pierwsze sprawdzenie od razu.
         */
        checkStatus();

        /*
        |--------------------------------------------------------------------------
        | Ładowanie GLB
        |--------------------------------------------------------------------------
        */

        function loadGlb(glbUrl) {

            console.log(
                'Model GLB gotowy:',
                glbUrl
            );

            /*
             * Tymczasowo.
             * Tutaj później podłączymy właściwy viewer GLB.
             */
            viewer.innerHTML = '';

            const message = document.createElement('div');

            message.textContent =
                'Model GLB gotowy do wyświetlenia.';

            viewer.appendChild(message);
        }
    </script>

</body>

</html>