<?php
declare(strict_types=1);
?>
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#101a1d">
    <title>Image → 3D — tryb wielozdjęciowy</title>
    <script type="importmap">
    {
        "imports": {
            "three": "https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js",
            "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.180.0/examples/jsm/"
        }
    }
    </script>
    <link rel="stylesheet" href="assets/css/multiphoto.css">
    <script type="module" src="assets/js/multiphoto.js"></script>
</head>
<body>
    <header class="topbar">
        <a class="brand" href="index.php"><span aria-hidden="true">◈</span> Image → 3D</a>
        <span class="mode-label">API v1 · tryb wielozdjęciowy</span>
    </header>

    <main class="page">
        <section class="intro">
            <p class="eyebrow">WIELE KLATEK / WERSJONOWANY MODEL</p>
            <h1>Rekonstrukcja z wielu zdjęć</h1>
            <p>Dodaj oryginalne obrazy i jawne metadane dla każdej klatki. API nie tworzy brakujących danych śledzenia.</p>
        </section>

        <aside class="notice notice-warning" role="note">
            <strong>Ważne — ta strona nie wykonuje śledzenia ARCore.</strong>
            <p>Przeglądarka nie dostarcza tu przyjętego źródła Android ARCore. Dla każdego obrazu zaimportuj lub wklej kompletny JSON metadanych pochodzący z zewnętrznego, zaufanego źródła (np. kontrolowanego przepływu developerskiego). Nie wpisuj szacowanych póz, intrinsics, macierzy identyczności ani innych wartości jako pomiarów.</p>
            <p><code>systemSessionId</code> identyfikuje logiczny skan, niezależnie od <code>arSessionEpochId</code>. Klatki w jednym skanie mogą pochodzić z różnych epok AR i mieć różne <code>referenceFrameId</code>, ale każda musi zawierać jawne <code>cameraToFirstFrame</code> wyrażone we wspólnym układzie całego skanu. Strona nie używa ani nie zastępuje go przez <code>cameraToSystemSessionFrame</code>. <code>cameraProfile</code> musi pozostać stabilny w sesji. <code>deviceId</code> jest identyfikatorem deklarowanym przez klienta, a nie uwierzytelnieniem ani dowodem tożsamości.</p>
        </aside>

        <section class="panel" aria-labelledby="session-heading">
            <div class="section-heading">
                <div>
                    <p class="eyebrow">01 / SESJA</p>
                    <h2 id="session-heading">Utwórz lub wznów</h2>
                </div>
                <span id="connection-state" class="pill">Brak aktywnej sesji</span>
            </div>

            <div class="form-grid">
                <label for="device-id">Client deviceId
                    <input id="device-id" type="text" maxlength="128" autocomplete="off" spellcheck="false">
                    <span class="field-help">Wartość jest przechowywana w tej przeglądarce. API wznowi aktywną sesję przypisaną do tego identyfikatora.</span>
                </label>
                <button id="create-session" class="button button-primary" type="button">Utwórz / wznów sesję</button>
            </div>
            <div class="form-grid form-grid-open">
                <label for="open-session-id">Otwórz istniejący systemSessionId
                    <input id="open-session-id" type="text" maxlength="32" placeholder="32 znaki hex" autocomplete="off" spellcheck="false">
                </label>
                <button id="open-session" class="button" type="button">Odczytaj status</button>
            </div>
            <div id="session-summary" class="session-summary" hidden>
                <div><span>systemSessionId</span><code id="active-session-id"></code></div>
                <div><span>Status</span><strong id="session-status">—</strong></div>
                <div><span>Opublikowana wersja</span><strong id="current-version">0</strong></div>
                <button id="complete-session" class="button button-danger" type="button">Zakończ / zamknij przyjmowanie klatek</button>
            </div>
        </section>

        <section class="panel" aria-labelledby="capture-heading">
            <div class="section-heading">
                <div>
                    <p class="eyebrow">02 / OBRAZY I METADANE</p>
                    <h2 id="capture-heading">Dodaj klatki</h2>
                </div>
                <span id="queue-count" class="subtle">0 obrazów</span>
            </div>
            <p class="field-help">Każdy upload zawiera jeden oryginalny plik <code>photo</code> oraz jeden obiekt JSON <code>metadata</code>. Limit API: 1 B–20 MiB na JPEG, PNG lub WebP. Pliki nie są zmieniane ani ponownie kodowane; uploady zbiorcze odbywają się kolejno.</p>
            <label class="file-picker" for="image-files">
                <span aria-hidden="true">＋</span>
                <span>Wybierz wiele obrazów</span>
                <input id="image-files" type="file" accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp" multiple disabled>
            </label>
            <div class="toolbar">
                <button id="upload-all" class="button button-primary" type="button" disabled>Wyślij gotowe klatki</button>
                <button id="refresh-status" class="button" type="button" disabled>Odśwież status</button>
                <span id="upload-message" class="subtle" role="status" aria-live="polite"></span>
            </div>
            <div id="frame-queue" class="frame-queue" aria-live="polite"></div>
        </section>

        <section class="panel" aria-labelledby="status-heading">
            <div class="section-heading">
                <div>
                    <p class="eyebrow">03 / PRZETWARZANIE</p>
                    <h2 id="status-heading">Status klatek</h2>
                </div>
                <span id="poll-indicator" class="subtle">Polling co 3 s</span>
            </div>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Sequence</th><th>Frame ID</th><th>Status</th><th>Postęp</th><th>Błąd</th></tr></thead>
                    <tbody id="server-frames">
                        <tr><td colspan="5" class="empty-state">Połącz z sesją, aby pobrać status klatek.</td></tr>
                    </tbody>
                </table>
            </div>
        </section>

        <section class="panel model-panel" aria-labelledby="model-heading">
            <div class="section-heading">
                <div>
                    <p class="eyebrow">04 / WYNIK</p>
                    <h2 id="model-heading">Wersjonowany model GLB</h2>
                </div>
                <a id="download-model" class="button" href="#" hidden>Przejdź do pobrania GLB</a>
            </div>
            <p id="model-message" class="subtle" role="status" aria-live="polite">Brak opublikowanego modelu.</p>
            <button id="retry-model" class="button" type="button" hidden>Ponów pobranie podglądu</button>
            <div id="model-viewer" class="model-viewer" aria-label="Interaktywny podgląd modelu 3D" aria-busy="false"></div>
        </section>

        <details class="panel contract-panel">
            <summary>Wymagane pola metadata v1</summary>
            <p>Zaimportuj JSON utworzony przez zewnętrzne źródło dla danego obrazu. Strona sprawdzi strukturę, bajty obrazu, MIME, wymiary i SHA-256, ale nie wylicza ani nie uzupełnia wartości pomiarowych. Dodatkowe pola metadanych przechwycenia są zachowywane; <code>systemSessionId</code> identyfikuje zasób sesji osobno i nie należy do metadanych ramki.</p>
            <code class="contract-fields">frameId, sequence, timestampMs, trackingState, assetId, sha256, mimeType, width, height, orientation, imageTransform, arSessionEpochId, referenceFrameId, cameraToFirstFrame, intrinsics, distortionStatus, cameraProfile</code>
            <p><code>cameraToFirstFrame</code> zawiera <code>translationM: [x,y,z]</code> w metrach oraz znormalizowany <code>rotationQuaternionXyzw: [x,y,z,w]</code>. Dla <code>sequence: 0</code> pozycja musi być tożsamościowa: translacja [0,0,0] i quaternion [0,0,0,±1]. Każda pozycja musi być jawnie podana we wspólnym układzie logicznego skanu — UI nie przelicza jej na podstawie epoki ani identyfikatora ramy odniesienia i nie akceptuje zastępczego pola <code>cameraToSystemSessionFrame</code>. <code>intrinsics</code> są specyficzne dla obrazu. Metadane pozy, intrinsics, transformacji obrazu i epoch pozostają częścią danych przechwycenia. Nie wysyłaj <code>mogeToCameraMatrix4x4</code>, <code>scaleEstimate</code> ani <code>axes</code>: kanoniczna konwencja metryczna MoGe v3 pochodzi wyłącznie z zaufanego sidecara udanego workera; przy braku lub nieprawidłowym sidecarze agregacja kończy się błędem bez publikacji nowego modelu. <code>distortionStatus: "not_provided"</code> oznacza brak danych o dystorsji, nie dystorsję zerową.</p>
        </details>

        <div id="global-error" class="error-banner" role="alert" hidden></div>
    </main>

    <footer><a href="index.php">← Powrót do trybu pojedynczego zdjęcia</a></footer>
</body>
</html>
