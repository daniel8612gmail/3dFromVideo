<?php

function resolveLanguage(): string
{
    $supportedLanguages = ['pl', 'en'];
    $requestedLanguage = $_GET['lang'] ?? null;

    if (
        is_string($requestedLanguage)
        && in_array($requestedLanguage, $supportedLanguages, true)
    ) {
        setcookie(
            'img3d_lang',
            $requestedLanguage,
            [
                'expires' => time() + 31536000,
                'path' => '/',
                'secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off',
                'httponly' => true,
                'samesite' => 'Lax'
            ]
        );

        return $requestedLanguage;
    }

    $savedLanguage = $_COOKIE['img3d_lang'] ?? null;

    if (
        is_string($savedLanguage)
        && in_array($savedLanguage, $supportedLanguages, true)
    ) {
        return $savedLanguage;
    }

    $acceptedLanguages = [];
    $header = $_SERVER['HTTP_ACCEPT_LANGUAGE'] ?? '';

    foreach (explode(',', $header) as $position => $entry) {
        $parts = explode(';', trim($entry));
        $locale = strtolower(trim($parts[0]));
        $quality = 1.0;

        if (isset($parts[1]) && preg_match('/^\s*q=([0-9.]+)\s*$/i', $parts[1], $matches)) {
            $quality = (float) $matches[1];
        }

        if ($locale !== '' && $quality > 0) {
            $acceptedLanguages[] = [
                'locale' => $locale,
                'quality' => $quality,
                'position' => $position
            ];
        }
    }

    usort(
        $acceptedLanguages,
        static function (array $left, array $right): int {
            if ($left['quality'] === $right['quality']) {
                return $left['position'] <=> $right['position'];
            }

            return $right['quality'] <=> $left['quality'];
        }
    );

    foreach ($acceptedLanguages as $acceptedLanguage) {
        $localeLanguage = explode('-', $acceptedLanguage['locale'])[0];

        if (in_array($localeLanguage, $supportedLanguages, true)) {
            return $localeLanguage;
        }
    }

    return 'pl';
}

function getTranslations(string $language): array
{
    $translations = [
        'pl' => [
            'nav_about' => 'O projekcie',
            'nav_how' => 'Jak to działa',
            'nav_applications' => 'Zastosowania',
            'nav_roadmap' => 'Rozwój',
            'try_app' => 'Wypróbuj aplikację',
            'menu_open' => 'Otwórz nawigację',
            'menu_close' => 'Zamknij nawigację',
            'hero_eyebrow' => 'Computer vision · geometria · architektura',
            'hero_title' => 'Od zdjęcia do geometrii 3D',
            'hero_description' => 'Eksperymentalny system wykorzystujący analizę obrazu do odtwarzania uproszczonej geometrii elementów architektury na podstawie fotografii. Sysytem wyklucza ze zdjęcia elementy o nieregularnych kształtach i koncentruje się na dominujących płaszczyznach, z których generuje lekki model 3D.',
            'hero_primary' => 'Wypróbuj aplikację',
            'hero_secondary' => 'Poznaj technologię',
            'concept_visual' => 'Wizualizacja koncepcyjna — nie jest wynikiem działania algorytmu.',
            'best_results' => 'Najleprze rezultaty można osiągnąć przesyłąjąc zdjęcia przedstawiające budynki.',
            'visual_input' => '01 / FOTOGRAFIA',
            'visual_planes' => '02 / PŁASZCZYZNY',
            'visual_model' => '03 / GEOMETRIA',
            'about_eyebrow' => 'O projekcie',
            'about_title' => 'Architektura opisana geometrią',
            'about_lead' => 'Image → 3D bada, jak z pojedynczego obrazu wydobyć główne płaszczyzny budynku i zamienić je w lekką geometrię.',
            'about_body' => 'Zamiast dążyć do fotorealistycznego odtworzenia każdego detalu, projekt skupia się na dominujących powierzchniach i pomija nieregularne elementy, które utrudniają uproszczoną rekonstrukcję. Wynikiem procesu jest model 3D, który można pobrać jako plik GLB.',
            'fact_single_photo' => 'Pojedyncza fotografia jako wejście',
            'fact_planes' => 'Dominujące płaszczyzny architektury',
            'fact_geometry' => 'Lekka geometria zamiast samej chmury punktów',
            'fact_glb' => 'Eksport wyniku do formatu GLB',
            'how_eyebrow' => 'Przepływ pracy',
            'how_title' => 'Od obrazu do modelu',
            'how_description' => 'Cztery etapy pokazują założony przepływ pracy — szczegóły analizy i rezultat zależą od przetwarzania.',
            'steps' => [
                ['title' => 'Zdjęcie wejściowe', 'body' => 'Wybierz fotografię architektury z urządzenia. '],
                ['title' => 'Analiza obrazu', 'body' => 'System szuka dominujących płaszczyzn i cech geometrycznych.'],
                ['title' => 'Budowa geometrii', 'body' => 'Rozpoznane powierzchnie stanowią podstawę uproszczonego modelu.'],
                ['title' => 'Eksport modelu', 'body' => 'Po poprawnym zakończeniu pobierz wynik jako plik GLB.']
            ],
            'app_eyebrow' => 'Interaktywne narzędzie',
            'app_title' => 'Wypróbuj Image → 3D',
            'app_description' => 'Wczytaj zdjęcie, śledź postęp przetwarzania i obejrzyj model, gdy będzie gotowy.',
            'app_session' => 'Sesja robocza',
            'applications_eyebrow' => 'Możliwości i kierunki',
            'applications_title' => 'Od tego, co działa, do tego, co można rozwinąć',
            'current_capabilities' => 'Dostępne w aplikacji',
            'current_capabilities_body' => 'Obecna wersja przyjmuje pojedyncze zdjęcie, uruchamia proces generowania, pokazuje jego status, wyświetla dostępny model 3D i umożliwia pobranie pliku GLB.',
            'potential_uses' => 'Potencjalne zastosowania',
            'potential_note' => 'To kierunki wykorzystania technologii, a nie gwarantowane funkcje obecnej wersji.',
            'potential_items' => [
                'Uproszczone modele budynków',
                'Prototypowanie geometrii architektonicznej',
                'Lekkie zasoby 3D do aplikacji internetowych',
                'Eksperymenty z rekonstrukcją scen z obrazów'
            ],
            'roadmap_eyebrow' => 'Kierunki prac',
            'roadmap_title' => 'Technologia w rozwoju',
            'roadmap_description' => 'Możliwe obszary dalszych eksperymentów — bez deklarowania terminów ani dostępności funkcji.',
            'roadmap_items' => [
                'Lepsze wykrywanie płaszczyzn',
                'Obsługa bardziej złożonych elementów architektury',
                'Rozwój rekonstrukcji geometrii i tekstur',
                'Więcej zdjęć oraz dalszy rozwój eksportu'
            ],
            'closing_eyebrow' => 'Zrób pierwszy krok',
            'closing_title' => 'Zacznij od zdjęcia',
            'closing_description' => 'Sprawdź, jak fotografia może posłużyć jako punkt wyjścia do budowy uproszczonego modelu 3D.',
            'closing_cta' => 'Przejdź do aplikacji',
            'footer_description' => 'Eksperymentalny projekt na styku analizy obrazu i geometrii 3D.',
            'footer_navigation' => 'Nawigacja',
            'footer_language' => 'Wersje językowe',
            'footer_top' => '↑ Na górę',
            'description' => 'System przeznaczony do generowania modelu 3D dla elementów architektury z pojedynczego zdjęcia.',
            'description_details' => 'Jego celem jest wyszukanie dominujących płaszczyzn z pominięciem nieregularnych obiektów i stworzenie lekkiego modelu geometrycznego na podstawie odnalezionych płaszczyzn.',
            'session_id' => 'Identyfikator sesji:',
            'created' => 'Utworzono:',
            'upload_photo' => 'Wczytaj zdjęcie z urządzenia',
            'new_session' => 'Nowa sesja',
            'download_model' => 'Pobierz model GLB',
            'selected_file' => 'Wybrano:',
            'image_preview' => 'Podgląd załadowanego zdjęcia',
            'status_label' => 'Status:',
            'waiting' => 'oczekiwanie',
            'uploading' => 'wysyłanie',
            'uploaded' => 'przesłano',
            'processing' => 'przetwarzanie, może to zająć kilka minut',
            'ready' => 'gotowe',
            'error' => 'błąd',
            'viewer_placeholder' => 'Podgląd modelu 3D pojawi się tutaj.',
            'invalid_image_type' => 'Nieprawidłowy typ pliku. Wybierz JPG, PNG lub WEBP.',
            'file_too_large' => 'Plik jest za duży. Maksymalny rozmiar to 20 MB.',
            'image_read_error' => 'Nie udało się odczytać obrazu.',
            'photo_restore_error' => 'Nie udało się wczytać wcześniej przesłanego zdjęcia.',
            'uploaded_photo' => 'Przesłane zdjęcie',
            'image_resize_error' => 'Nie udało się przeskalować obrazu.',
            'upload_failed' => 'Upload zdjęcia nie powiódł się.',
            'image_processing_error' => 'Wystąpił błąd podczas przetwarzania zdjęcia.',
            'glb_read_error' => 'Nie udało się odczytać modelu GLB.',
            'glb_download_error' => 'Nie udało się pobrać modelu GLB. Spróbuj ponownie.',
            'session_status_error' => 'Nie udało się pobrać statusu sesji.',
            'model_processing_error' => 'Wystąpił błąd podczas przetwarzania modelu.',
            'rate_title' => 'Za dużo żądań',
            'rate_limit_prefix' => 'Możesz utworzyć maksymalnie',
            'rate_limit_suffix' => 'sesje w ciągu minuty.',
            'retry_prefix' => 'Spróbuj ponownie za około',
            'retry_suffix' => 's.',
            'session_create_error' => 'Nie udało się utworzyć katalogu sesji.',
            'server_errors' => []
        ],
        'en' => [
            'nav_about' => 'About',
            'nav_how' => 'How it works',
            'nav_applications' => 'Applications',
            'nav_roadmap' => 'Roadmap',
            'try_app' => 'Try the app',
            'menu_open' => 'Open navigation',
            'menu_close' => 'Close navigation',
            'hero_eyebrow' => 'Computer vision · geometry · architecture',
            'hero_title' => 'From photograph to 3D geometry',
            'hero_description' => 'An experimental system using image analysis to reconstruct simplified architectural geometry from a photograph.',
            'hero_primary' => 'Try the app',
            'hero_secondary' => 'Explore the technology',
            'concept_visual' => 'Concept visualization — not an output produced by the algorithm.',
            'visual_input' => '01 / PHOTOGRAPH',
            'visual_planes' => '02 / PLANES',
            'visual_model' => '03 / GEOMETRY',
            'about_eyebrow' => 'About the project',
            'about_title' => 'Architecture, described through geometry',
            'about_lead' => 'Image → 3D explores how to extract a building’s main planes from a single image and turn them into lightweight geometry.',
            'about_body' => 'Rather than aiming to recreate every detail photorealistically, the project focuses on dominant surfaces and skips irregular elements that complicate simplified reconstruction. The process produces a 3D model that can be downloaded as a GLB file.',
            'fact_single_photo' => 'A single photograph as input',
            'fact_planes' => 'Dominant architectural planes',
            'fact_geometry' => 'Lightweight geometry, not only a point cloud',
            'fact_glb' => 'Export to the GLB format',
            'how_eyebrow' => 'Workflow',
            'how_title' => 'From image to model',
            'how_description' => 'These four stages describe the intended workflow; analysis details and results depend on processing.',
            'steps' => [
                ['title' => 'Input photograph', 'body' => 'Choose an architectural photograph from your device.'],
                ['title' => 'Image analysis', 'body' => 'The system searches for dominant planes and geometric features.'],
                ['title' => 'Geometry generation', 'body' => 'Recognized surfaces provide the basis for a simplified model.'],
                ['title' => 'Model export', 'body' => 'When processing completes successfully, download the result as a GLB file.']
            ],
            'app_eyebrow' => 'Interactive tool',
            'app_title' => 'Try Image → 3D',
            'app_description' => 'Upload a photo, follow processing progress, and view the model when it is ready.',
            'app_session' => 'Workspace session',
            'applications_eyebrow' => 'Capabilities and directions',
            'applications_title' => 'From what works today to what could grow',
            'current_capabilities' => 'Available in the app',
            'current_capabilities_body' => 'The current version accepts a single photo, starts model generation, reports its status, displays an available 3D model, and lets you download a GLB file.',
            'potential_uses' => 'Potential applications',
            'potential_note' => 'These are possible directions for the technology, not guaranteed features of the current version.',
            'potential_items' => [
                'Simplified building models',
                'Architectural geometry prototyping',
                'Lightweight 3D assets for web applications',
                'Experiments in reconstructing scenes from images'
            ],
            'roadmap_eyebrow' => 'Areas to explore',
            'roadmap_title' => 'A technology in development',
            'roadmap_description' => 'Possible areas for further experimentation, without promises about timelines or feature availability.',
            'roadmap_items' => [
                'Improved plane detection',
                'Support for more complex architectural elements',
                'Further geometry and texture reconstruction',
                'More images and continued export development'
            ],
            'closing_eyebrow' => 'Take the first step',
            'closing_title' => 'Start with a photograph',
            'closing_description' => 'See how a photograph can become the starting point for a simplified 3D model.',
            'closing_cta' => 'Go to the app',
            'footer_description' => 'An experimental project at the intersection of image analysis and 3D geometry.',
            'footer_navigation' => 'Navigation',
            'footer_language' => 'Languages',
            'footer_top' => '↑ Back to top',
            'description' => 'Generate a 3D model of architectural elements from a single photograph.',
            'description_details' => 'The system identifies dominant planes while ignoring irregular objects, then creates a lightweight geometric model from the detected planes.',
            'session_id' => 'Session ID:',
            'created' => 'Created:',
            'upload_photo' => 'Choose a photo from your device',
            'new_session' => 'New session',
            'download_model' => 'Download GLB model',
            'selected_file' => 'Selected:',
            'image_preview' => 'Preview of the uploaded photo',
            'status_label' => 'Status:',
            'waiting' => 'waiting',
            'uploading' => 'uploading',
            'uploaded' => 'uploaded',
            'processing' => 'processing',
            'ready' => 'ready',
            'error' => 'error',
            'viewer_placeholder' => 'The 3D model preview will appear here.',
            'invalid_image_type' => 'Unsupported file type. Choose a JPG, PNG, or WEBP image.',
            'file_too_large' => 'The file is too large. The maximum size is 20 MB.',
            'image_read_error' => 'Could not read the image.',
            'photo_restore_error' => 'Could not load the previously uploaded photo.',
            'uploaded_photo' => 'Uploaded photo',
            'image_resize_error' => 'Could not resize the image.',
            'upload_failed' => 'The photo upload failed.',
            'image_processing_error' => 'An error occurred while processing the photo.',
            'glb_read_error' => 'Could not read the GLB model.',
            'glb_download_error' => 'Could not download the GLB model. Please try again.',
            'session_status_error' => 'Could not retrieve the session status.',
            'model_processing_error' => 'An error occurred while processing the model.',
            'rate_title' => 'Too many requests',
            'rate_limit_prefix' => 'You can create up to',
            'rate_limit_suffix' => 'sessions per minute.',
            'retry_prefix' => 'Please try again in about',
            'retry_suffix' => 's.',
            'session_create_error' => 'Could not create the session directory.',
            'server_errors' => [
                'Dozwolona jest tylko metoda POST.' => 'Only POST requests are allowed.',
                'Nieprawidłowy identyfikator sesji.' => 'Invalid session ID.',
                'Sesja nie istnieje.' => 'The session does not exist.',
                'Nieprawidłowa ścieżka sesji.' => 'Invalid session path.',
                'Nie przesłano zdjęcia.' => 'No photo was uploaded.',
                'Plik przekracza limit serwera.' => 'The file exceeds the server limit.',
                'Plik przekracza dozwolony rozmiar.' => 'The file exceeds the allowed size.',
                'Plik został przesłany tylko częściowo.' => 'The file was only partially uploaded.',
                'Nie przesłano pliku.' => 'No file was uploaded.',
                'Brak katalogu tymczasowego.' => 'The temporary directory is missing.',
                'Nie można zapisać pliku.' => 'The file could not be saved.',
                'Upload został zatrzymany przez rozszerzenie PHP.' => 'The upload was stopped by a PHP extension.',
                'Nieznany błąd uploadu.' => 'Unknown upload error.',
                'Plik jest za duży. Maksymalny rozmiar to 20 MB.' => 'The file is too large. The maximum size is 20 MB.',
                'Nieprawidłowy upload pliku.' => 'Invalid file upload.',
                'Przesłany plik nie jest prawidłowym obrazem.' => 'The uploaded file is not a valid image.',
                'Dozwolone są tylko pliki JPG, PNG i WEBP.' => 'Only JPG, PNG, and WEBP files are allowed.',
                'Zdjęcie zostało już przesłane dla tej sesji.' => 'A photo has already been uploaded for this session.',
                'Nie udało się zapisać zdjęcia.' => 'Could not save the photo.',
                'Nie udało się zapisać stanu sesji.' => 'Could not save the session state.'
            ]
        ]
    ];

    return $translations[$language];
}
