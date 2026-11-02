# Architektura projektu 3D From Video

## Cel i aktualny stan

3D From Video jest prototypem systemu przekształcającego dane wizualne w lekkie modele 3D w formacie GLB. Priorytetem jest odtworzenie głównych brył i płaszczyzn, szczególnie elementów architektonicznych, bez generowania ciężkich chmur punktów.

System zachowuje legacy przepływ **pojedyncze zdjęcie → model GLB** i dodaje przepływ **wiele zdjęć → sesja systemowa → wersjonowany model GLB**. W tym drugim workery przetwarzają klatki niezależnie i równolegle, a osobny agent sumujący dodaje ukończone geometrie do modelu sesji. Aplikacja Android jest poza zakresem repozytorium; backend udostępnia kontrakt API dla klienta. Narzędzia do pracy z plikami wideo są osobną ścieżką i nie stanowią jeszcze kompletnego przepływu video-to-3D.

## Widok systemu

```text
Użytkownik
   │
   ▼
Klient webowy / aplikacja Android (zewnętrzna)
   │ PHP + JavaScript / API HTTP: sesja, upload, status i wersje GLB
   ▼
PHP: system/web_img3d
   │
   ├── legacy: data/{sessionId}/photo.* + state.json
   └── multi-photo: data/system-sessions/{systemSessionId}/frames/*
   │
   ▼
Broker Node.js / WebSocket: system/img3d_ws
   ├── rozdziela klatki do workerów obrazu (równolegle, z limitem puli)
   │      └── system/img3d_ws_agent → MoGe-3 → geom_process.py → GLB klatki
   ├── durable outbox: wynik GLB + metadane do agenta sumującego
   │      └── system/img3d_ws_aggregator → geom_publish_glb.py
   │             └── geom_aggregate_glb.py → geometria + atlas tekstur
   └── data/system-sessions/{systemSessionId}/model.vN.glb
          + current-version.json → API status/model → podgląd Three.js lub klient
```

W typowym wdrożeniu serwer WWW udostępnia PHP przez HTTPS, a reverse proxy przekazuje połączenia WSS do usługi Node.js. Serwer WebSocket domyślnie nasłuchuje na `127.0.0.1`, więc dostęp z zewnątrz wymaga odpowiedniej konfiguracji proxy.

## Główne komponenty

### Interfejs webowy — `system/web_img3d/`

- `index.php` ładuje tłumaczenia, ogranicza częstotliwość tworzenia sesji, wznawia poprawną sesję albo tworzy nową.
- `includes/session.php` generuje identyfikator sesji jako 32 znaki szesnastkowe i zapisuje początkowy stan.
- `upload.php` przyjmuje zdjęcie metodą POST, sprawdza poprawność obrazu i dozwolony MIME type (JPEG, PNG, WEBP), ogranicza rozmiar do 20 MB i zapisuje je w katalogu sesji.
- `status.php` udostępnia stan sesji przez GET. Gdy stan jest `ready`, sprawdza obecność pliku GLB i zwraca ścieżkę do niego.
- `get-glb.php` i `get-photo.php` udostępniają pliki sesji, a skrypty `assets/js/` obsługują interakcje, status, podgląd zdjęcia i modelu.
- `assets/js/viewer.js` odpowiada za podgląd modelu w przeglądarce.
- `multiphoto.php` i `api/v1/` udostępniają stronę demonstracyjną oraz API tworzenia sesji systemowej, dodawania klatek, odczytu postępu, zamknięcia sesji i pobierania niezmiennych wersji GLB.

Interfejs i usługi backendowe współdzielą dane sesji przez katalog `data`. Aplikacja używa stanu plikowego zamiast centralnej bazy danych.

### Usługa WebSocket — `system/img3d_ws/`

- `src/server.js` uruchamia serwer WebSocket, autoryzuje workery i obsługuje ich komunikaty.
- `src/agents.js` przechowuje konfigurację autoryzowanych i podłączonych agentów.
- `src/jobs.js` wyszukuje sesje ze stanem `uploaded`, przypisuje zadanie wolnemu workerowi, aktualizuje `state.json`, zapisuje wynik GLB i obsługuje błędy lub rozłączenia.
- `src/system-session-jobs.js` równolegle planuje klatki w obrębie wielu sesji oraz utrwala ukończone GLB i metadane w outboxie do ponownego przekazania sumatorowi.
- Obserwator plików wykrywa nowe zdjęcia w katalogu danych i inicjuje skanowanie oczekujących zadań. Skanowanie jest również uruchamiane po zdarzeniach związanych z workerami i zadaniami, np. po podłączeniu workera lub zakończeniu zadania.
- Serwer dopuszcza do 200 MB dla payloadu WebSocket; limit uploadu HTTP w PHP wynosi 20 MB.

Po stronie usługi Node.js konfiguracja obejmuje między innymi `DATA_DIR`, `PORT` i `AGENTS_FILE`. Przykładowy model wdrożenia i reverse proxy opisuje `system/img3d_ws/Readme.md`.

### Worker — `system/img3d_ws_agent/`

Worker łączy się z serwerem WSS, uwierzytelnia przy użyciu identyfikatora i tokenu agenta, odbiera opis zadania oraz binarne dane zdjęcia. Każde połączenie obsługuje jedno zadanie naraz; pula workerów może jednak przetwarzać wiele klatek tej samej lub różnych sesji równolegle. Worker zapisuje zdjęcie w izolowanym katalogu klatki, uruchamia istniejący pipeline i zwraca GLB pojedynczego ujęcia.

W obecnej implementacji główne etapy to przygotowanie pliku, uruchomienie MoGe-3, rekonstrukcja geometrii i odczyt wynikowego GLB. Skrypty Python są uruchamiane jako procesy potomne; kod zakończenia procesu wpływa na powodzenie etapu.

### Agent sumujący — `system/img3d_ws_aggregator/`

Jest to osobny, długowieczny proces Node.js, uwierzytelniany przez istniejący serwer WebSocket jako rola `aggregator`. Odbiera trwale zakolejkowane GLB klatek z brokera, potwierdza ich odbiór i uruchamia `system/py/geom_publish_glb.py`. Publisher korzysta z `geom_aggregate_glb.py`, scala klatkę z wersją bazową, odrzuca wiarygodne duplikaty płaszczyzn i łączy tekstury do atlasów. Publikacja nowego `model.vN.glb` i wskaźnika `current-version.json` jest wersjonowana i atomowa. Zadania jednej sesji są serializowane, ale różne sesje mogą być sumowane niezależnie.

### Pipeline obrazu — `system/py/`

- `ai_moge3.py` uruchamia lokalny model MoGe-3 i zapisuje wyniki inferencji (m.in. punkty, głębię, maskę i normalne) do pliku `moge3.pt`.
- `geom_process.py` używa tych danych do grupowania kierunków normalnych i płaszczyzn, wyznaczania prostokątnych regionów oraz teksturowania ich z obrazu.
- Moduły `geom_*` realizują etapy rekonstrukcji i eksportu. Wyniki pośrednie i debugowe mogą być zapisywane w podkatalogu obrazu.
- Worker oczekuje pliku GLB w podkatalogu obrazu, a następnie przesyła jego zawartość binarną do usługi WebSocket.
- `geom_aggregate_glb.py` ustawia zarejestrowane geometrie w układzie sesji, scala odpowiednio nakładające się współpłaszczyznowe prostokątne fragmenty i buduje wspólny atlas UV. `geom_publish_glb.py` aplikuje pojedynczy wkład do wersjonowanej sceny sesji.

Kod inferencji aktualnie wybiera urządzenie CUDA (`DEVICE = "cuda"`), więc dostępność odpowiedniego środowiska GPU i lokalnego modelu jest istotnym warunkiem uruchomienia pipeline.

## Przepływ danych dla zdjęcia

Poniższy opis dotyczy zachowanego legacy przepływu jednego zdjęcia i pliku `model.glb`.

1. Użytkownik otwiera stronę. PHP wznawia istniejącą sesję po prawidłowym `sessionId` albo tworzy nową.
2. Katalog `data/{sessionId}/` otrzymuje początkowy `state.json`, a sesja ma stan oczekiwania.
3. Przeglądarka wysyła zdjęcie do `upload.php`. Po walidacji PHP zapisuje `photo.jpg`, `photo.png` lub `photo.webp` oraz ustawia stan `uploaded`.
4. Obserwator serwera WebSocket wykrywa plik i inicjuje skanowanie oczekujących sesji. Serwer wybiera bezczynnego workera, tworzy `jobId`, zmienia stan sesji na `processing` i wysyła metadane zadania oraz zdjęcie. Skanowanie jest ponawiane również po wybranych zdarzeniach obsługi workerów i zadań.
5. Worker uruchamia pipeline: zapis wejścia, inferencja MoGe-3, rekonstrukcja geometrii i odczyt pliku GLB.
6. Worker raportuje postęp przez komunikaty WebSocket. Serwer zapisuje postęp w `state.json`.
7. Po otrzymaniu GLB serwer sprawdza nagłówek `glTF`, zapisuje wynik jako `model.glb` i ustawia stan `ready` z postępem 100%.
8. Przeglądarka odczytuje stan przez PHP i udostępnia podgląd lub pobranie modelu.

### Kontrakt sesji i zadania

Katalog sesji jest wspólnym punktem wymiany pomiędzy PHP a backendem. Typowe pliki to:

```text
data/{sessionId}/
├── state.json
├── photo.jpg | photo.png | photo.webp
└── model.glb
```

`sessionId` ma format 32 znaków hex. Stan zawiera co najmniej `createdOn`, `status` i `progress`; podczas przetwarzania backend może zapisać również `jobId` i identyfikator workera, a po sukcesie ścieżkę GLB. W praktyce występują statusy oczekiwania, `uploaded`, `processing`, `ready` i `error`; status początkowy interfejsu może być zlokalizowany.

Komunikacja worker–serwer używa komunikatów JSON dla autoryzacji, opisu zadania, postępu i błędów. Zdjęcie oraz końcowy GLB są przesyłane jako osobne wiadomości binarne. Wysyłka GLB jest poprzedzana komunikatem `ready_for_glb`.

## Przepływ sesji wielozdjęciowej

- `systemSessionId` oznacza jeden logiczny skan/serię zdjęć, a nie sesję ARCore ani urządzenie. Wiele urządzeń może równolegle tworzyć niezależne sesje systemowe.
- Klient wysyła każdą klatkę osobno wraz z identyfikatorem i kolejnością, timestampem, stanem trackingu, metadanymi obrazu, intrinsics oraz pozycją kamery względem układu pierwszej klatki.
- Klatka `sequence: 0` definiuje układ bazowy i ma transformację identity. Pozycja/orientacja nie musi być dla niej wyliczana przez Androida; dalsze klatki muszą mieć jawny pełny transform camera-to-first-frame.
- Broker może wysłać różne klatki w jednej sesji do różnych workerów równolegle. Wynik każdego workera jest trwale zapisywany wraz z metadanymi w outboxie, zanim zwolni on worker.
- Dedykowany agent sumujący przyjmuje każdy ukończony GLB klatki. Publikuje kolejną wersję modelu po jej dodaniu; ponowienia i restart korzystają ze stabilnego identyfikatora zadania, by nie dublować wkładu.
- API udostępnia postęp klatek oraz numer ostatniej opublikowanej wersji GLB. Klient może pobierać tę niezmienną wersję do podglądu podczas dalszego przetwarzania.
- Pełny schemat metadanych, endpointy, topologię agentów i konfigurację wdrożeniową opisuje [kontrakt API multi-photo](multiphoto_api.md).

Model MoGe-3, mapowanie osi i skala pochodzą ze zweryfikowanego pipeline’u/sidecara, a nie z pól dostarczanych przez Androida. Aktualnie agregacja przyjmuje jedynie kanoniczny, nieobracany i niekadrowany obraz; obsługę transformacji obrazu należy rozszerzyć przed użyciem innych orientacji/cropów.

## Przetwarzanie wideo — stan obecny

Repozytorium zawiera oddzielny mechanizm oparty na `system/watcher.js` i `system/videoProcessor.js`. Obserwator wykrywa wybrane pliki MP4 w strukturze `users/` i uruchamia zadania kalibracji lub przetwarzania. Kod procesora obejmuje m.in. ekstrakcję klatek przez FFmpeg, korekcję zniekształceń i narzędzia analizy klatek.

To osobna ścieżka pomocnicza. Nie jest jeszcze zintegrowana z API multi-photo: przyjmowaniem pliku MP4, wyborem klatek, synchronizacją pozy dla klatek filmu i przekazaniem ich do sesji systemowej. Pełny przepływ bezpośrednio z filmu pozostaje kierunkiem dalszego rozwoju.

## Uruchamianie i konfiguracja — ogólnie

Projekt wymaga środowisk odpowiednich dla poszczególnych warstw:

- serwera WWW z PHP dla interfejsu i endpointów;
- Node.js/npm dla głównego projektu, usługi WebSocket i workera (każda usługa ma własny katalog i manifest npm);
- oddzielnie uruchamianego procesu `system/img3d_ws_aggregator/` dla sesji wielozdjęciowych;
- Pythona oraz bibliotek wykorzystywanych przez skrypty `system/py/`;
- lokalnie dostępnego modelu MoGe-3 skonfigurowanego przez `MOGE_MODEL_PATH`;
- CUDA/GPU dla obecnej konfiguracji inferencji MoGe-3;
- wspólnego katalogu danych PHP i usługi WebSocket; worker otrzymuje zdjęcie przez WebSocket i zapisuje je w swoim katalogu roboczym, który może znajdować się na innej maszynie;
- sekretów i konfiguracji połączenia workera przechowywanych poza kodem, np. w środowisku procesu lub pliku `.env`.

Dokładna konfiguracja zależy od środowiska. Szczegóły instalacji usługi WebSocket są w `system/img3d_ws/Readme.md`, a główne założenia projektu w `Readme.md`.

## Granice odpowiedzialności przy rozwoju

- **UI webowe:** sesje użytkownika, upload, status i wizualizacja GLB.
- **Backend Node.js:** uwierzytelnienie workerów, kolejka, transport, postęp i zapis wyniku.
- **Worker:** połączenie z backendem i uruchomienie pipeline jako procesów.
- **Agent sumujący:** przyjmowanie gotowych GLB klatek, ich idempotentne scalanie i wersjonowanie modelu sesji.
- **Python:** inferencja, analiza obrazu, rekonstrukcja geometrii i eksport modelu.
- **Wideo:** osobna ścieżka wymagająca uzgodnienia kontraktów, jeśli ma zostać włączona do głównego przepływu aplikacji.

Zmiana formatu danych, statusów sesji, ścieżek plików lub komunikatów WebSocket może wymagać jednoczesnej aktualizacji kilku komponentów. Przed takim rozszerzeniem należy sprawdzić aktualnych producentów i konsumentów danego kontraktu.

## Testowanie

Testy są rozproszone pomiędzy katalogami. Testy multi-photo obejmują kontrakt i scheduler w `system/img3d_ws/test/`, protokół agenta w `system/img3d_ws_aggregator/tests/`, pipeline workerów w `system/img3d_ws_agent/tests/`, agregację geometrii w `system/py/tests/` oraz kontrakty PHP w `system/web_img3d/tests/`. Uruchomienie realnej inferencji i testu end-to-end nadal wymaga modeli, GPU oraz środowiska PHP/WebSocket z konfiguracją agentów i wspólnym storage.

Test jednostkowy pojedynczego modułu nie potwierdza pełnego przebiegu od uploadu do wyświetlenia GLB. Weryfikacja end-to-end wymaga środowiska z PHP, WebSocketem, workerem, modelem i zgodnym katalogiem danych.
