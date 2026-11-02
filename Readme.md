# 3D From Video

Projekt z obszaru generowania modeli 3D z danych wizualnych. Obsługuje generowanie GLB z pojedynczego zdjęcia oraz z serii zdjęć przypisanych do jednej sesji systemowej.

Tworzone modele 3D mają być możliwie proste i lekkie z zachowaniem płaszczyzn i pominięciem małych nieistotnych elementów oraz skomplikowanych kształtów, tak aby odtworzyć elementy architektury i główne elementy otaczającego świata.

Działanie systemu można sprawdzić na https://img3d.pcmagic.pl

## Status projektu

- Obecne tryby: legacy generowanie GLB z pojedynczego zdjęcia oraz wielozdjęciowe sesje z równoległym przetwarzaniem klatek i osobnym agentem sumującym
- Interfejs Android: kontrakt API jest opisany, aplikacja Android pozostaje poza zakresem repozytorium
- Plan rozwoju: generowanie modelu GLB z filmu
- Główne obszary: front-end webowy, połączenie z agentem AI, pipeline przygotowania geometrii i eksportu GLB

W kolejnej fazie rozwoju planowane jest rozszerzenie działania na materiał wideo, gdzie klatki będą analizowane sekwencyjnie i łączone w spójny model 3D. 

## Cel projektu

Celem projektu jest stworzenie kompletnego systemu do tworzenia modeli 3D o małym rozmiarze, które możn a będzie załadować na dużej liczbie urządzeń, w przeciwieństwie do popularnych chmór punktów.

- wykrywania obiektów i geometrii z obrazu,
- przygotowywania danych wejściowych dla modeli 3D,
- budowy prostych modeli geometrycznych,
- eksportu wyników do formatu GLB gotowego do wykorzystania w przeglądarkach, wizualizacjach i aplikacjach webowych.

## Główna architektura

Projekt składa się z kilku warstw:

1. Frontend webowy
   - katalog: system/web_img3d
   - odpowiada za upload zdjęcia, obsługę sesji, wyświetlanie stanu przetwarzania i podgląd wynikowego GLB
   - wykorzystuje PHP oraz skrypty frontendowe z podglądem Three.js

2. Warstwa komunikacyjna / WebSocket
   - katalog: system/img3d_ws
   - koordynuje sesje systemowe i równoległe zadania pojedynczych klatek, wysyła zdjęcia do workerów AI i przekazuje ukończone GLB do agregatora
   - zapisuje postęp, kolejkę oraz trwały outbox przekazujący wyniki

3. Agent AI / przetwarzanie
   - katalog: system/img3d_ws_agent
   - workery odbierają pojedyncze klatki, uruchamiają istniejący pipeline Python i zwracają GLB klatki

4. Agent sumujący
   - katalog: system/img3d_ws_aggregator
   - osobny, uwierzytelniony proces WebSocket odbiera GLB ukończonych klatek
   - uruchamia publisher Pythona, który scala geometrię i tekstury z modelem sesji oraz publikuje kolejną wersję GLB

5. Pipeline obróbki i AI
   - katalog: system/py
   - zawiera skrypty do detekcji, mapowania geometrii, kalibracji, ekstrakcji konturów, przetwarzania mask, budowy płaszczyzn i eksportu modeli 3D

6. Procesy pomocnicze i systemowe
   - katalog: system
   - zawiera watchery, kalibrację, przetwarzanie wideo i mechanizmy uruchamiania aplikacji

## Obecny workflow działania

Legacy workflow pojedynczego zdjęcia działa w następującym cyklu:

1. Użytkownik przesyła zdjęcie przez frontend z katalogu system/web_img3d.
2. PHP tworzy sesję i zapisuje stan w katalogu sesji.
3. Serwer WebSocket z system/img3d_ws sprawdza oczekujące zadania i przydziela je wolnemu agentowi.
4. Agent z system/img3d_ws_agent odbiera zdjęcie i uruchamia pipeline Python.
5. Pipeline przygotowuje dane 3D, tworzy geometrię i eksportuje poprawny plik GLB.
6. Plik GLB jest zapisany w katalogu sesji i dostępny dla frontendowego podglądu.
7. Stan sesji i postęp operacji są odświeżane w czasie rzeczywistym.

To jest obecnie funkcjonalna wersja beta i można ją traktować jako działający prototyp produktów typu Image-to-3D.

### Sesja wielozdjęciowa

API v1 pozwala utworzyć sesję systemową, przesyłać do niej zdjęcia z metadanymi pozy kamery, sprawdzać postęp i pobierać kolejne wersje modelu. Różne klatki mogą być przetwarzane równolegle przez workery. Pierwsza klatka (sequence 0) definiuje początek układu sesji; kolejne pozy są wyrażane względem niej. Osobny agent sumujący przyjmuje każdy ukończony GLB klatki i aktualizuje wersjonowany model główny.

Szczegóły endpointów, metadanych i wdrożenia opisuje [kontrakt API sesji wielozdjęciowej](doc/multiphoto_api.md). Aplikacja Android nie jest częścią repozytorium.

## Katalogi projektu

```text
3dFromVideo/
├── package.json
├── Readme.md
├── system/
│   ├── index.js
│   ├── watcher.js
│   ├── videoProcessor.js
│   ├── web_img3d/               # frontend aplikacji
│   ├── img3d_ws/                # serwer WebSocket + job orchestration
│   ├── img3d_ws_agent/          # agent AI po stronie wykonawczej
│   ├── img3d_ws_aggregator/     # osobny agent sumujący GLB klatek
│   ├── py/                      # skrypty AI / geometry / GLB export
│   ├── calibration/
│   └── ...
├── users/
├── test/
├── yolo26n.pt
├── yolo26n-seg.pt
└── ...
```

## Główne moduły

### Frontend

Katalog system/web_img3d obejmuje warstwę użytkownika:

- upload zdjęć,
- tworzenie sesji,
- kontrola statusu,
- odczyt i prezentacja modelu GLB,
- odświeżanie stanu w czasie pracy.

### WebSocket / orchestration

Katalog system/img3d_ws odpowiada za:

- autoryzację agentów,
- odbieranie zadań z UI,
- przydzielanie pracy odpowiedniemu agentowi,
- monitorowanie statusu sesji,
- odbiór danych binarnych i plików GLB,
- zapis końcowego wyniku do katalogu sesji.

### Agent AI
Agent jest to program przetwarzający zdjęcia. Odbiera zdjęcia z serwera. Działa w kilku etapach i przekazuje wykonany przez siebie model 3D na serwer. Może być uruchomiony na dowolnej maszynie z odpowiednią mocą obliczeniową dla modeli AI. Obecnie używa modelu sztucznej inteligencji MoGe-3 w celu wydobycia głębi i informacji o kierunku każdego z piksela obrazu.

Katalog system/img3d_ws_agent realizuje połączenie z serwerem i uruchamianie pipeline:

- nawiązuje połączenie WebSocket,
- odbiera zadania,
- pobiera zdjęcie od serwera,
- uruchamia skrypty z katalogu system/py,
- wysyła postęp wykonania,
- zwraca wynik GLB do serwera.

#### Instalacja
1. w katalogu img3d_ws_agent uruchom:
``` text
npm install
```

2. Zainstaluj Visual Studio Build Tools for C++ https://visualstudio.microsoft.com/visual-cpp-build-tools/
   Uruchom pobrany instalator.
   W zakładce Workloads zaznacz:
   - Desktop development with C++
   czyli Programowanie aplikacji klasycznych w języku C++.

   - Po prawej stronie upewnij się, że zaznaczone są przynajmniej:
      
      - MSVC v143 - VS 2022 C++ x64/x86 build tools
      - Windows 11 SDK albo Windows 10 SDK
      - C++ CMake tools for Windows 
3. Zainstaluj MoGe-3: https://github.com/microsoft/MoGe

   Na chwilę pisania dokumentacji są to komendy:
   ``` text
   pip install git+https://github.com/microsoft/MoGe.git
   ```
4. Ustawienie Ścieżki do modelu Moge-3:
``` text
przykład dla CMD:
set MOGE_MODEL_PATH=D:\AI3d\models\moge-3-vitl.pt

przykład dls PS
$env:MOGE_MODEL_PATH="C:\AI\model\moge-3-vitl.pt"
(działa do zamknięcia konsoli)
```
Po zmianie konieczny restart terminala

5. Zainstaluj: py torch

W zwykłym, legacy workflow pojedynczego zdjęcia wymagane jest `MOGE_MODEL_PATH`
i działający MoGe-3 — nie są wymagane zmienne `MOGE_EXPECTED_CODE_REVISION`
ani `MOGE_EXPECTED_CHECKPOINT_SHA256`. Worker przekazuje flagę
`--require-provenance` do skryptów Python wyłącznie dla zadań `system_frame`;
ten tryb multi-photo fail-closed wymaga obu pinów w workerze i po stronie
agregatora, a także zapisuje convention sidecar obok GLB. Nie uruchamiaj
skryptów z tą flagą dla legacy zadań image→GLB.

### Python pipeline

W katalogu system/py znajdują się narzędzia odpowiedzialne za:

- kalibrację kamery,
- detekcję krawędzi i regionów,
- segmentację i maskowanie,
- budowę geometrii,
- tworzenie płaszczyzn i granic,
- łączenie elementów w strukturę 3D,
- eksport do formatu GLB.

## Aktualne możliwości

W obecnym etapie działania projekt pozwala na:

- dodanie zdjęcia do systemu,
- zainicjowanie sesji przetwarzania,
- uruchomienie agenta AI,
- przygotowanie geometrycznego modelu 3D,
- zapis i odczyt wyniku w formacie GLB,
- pracy w trybie beta z prostym, działającym flow od zdjęcia do modelu 3D.

## Główne wymagania

Do uruchomienia projektu potrzebne są:

- Node.js
- npm
- Python 3
- Model AI MoGe-3
- biblioteki Python używane przez skrypty z katalogu system/py
- serwer web / proxy / WebSocket (w zależności od środowiska wdrożeniowego)
- odpowiednia konfiguracja agentów i tokenów dostępu

## Zespół agentów Copilot

W katalogu `.github/agents/` znajdują się współdzielone definicje agentów Copilot, którzy wspierają rozwój projektu w odrębnych rolach. To asystenci pracujący nad kodem i decyzjami projektowymi, a nie procesy workerów uruchamiane przez aplikację podczas przetwarzania zdjęć.

### Kontakt i koordynacja

- `project-manager.agent.md` — manager projektu i główny punkt kontaktu. Przyjmuje zadania od użytkownika, dobiera role, koordynuje zależności, zbiera wyniki i przedstawia użytkownikowi rezultat wraz z weryfikacją. Przy większych zmianach rozpoczyna od architekta, angażuje analityka zależnie od potrzeb i zleca testerowi niezależną weryfikację.

### Projektowanie i analiza

- `architect.agent.md` — architekt rozwiązania. Rozpoznaje obecny przepływ, wyznacza granice komponentów, kontrakty i etapy wdrożenia oraz koordynuje analityka, developerów i testera przy zadaniach obejmujących kilka warstw.
- `technical-analyst.agent.md` — analityk techniczny. Bada aktualnie dostępne modele AI, biblioteki, usługi i narzędzia; porównuje funkcje, integrację, wymagania sprzętowe, licencje, koszty oraz ryzyka na podstawie źródeł.

### Implementacja

- `ui-web.agent.md` — developer UI: PHP, JavaScript i CSS, upload, status sesji, komunikaty błędów oraz podgląd i pobieranie GLB.
- `backend-developer.agent.md` — developer backendu Node.js: WebSocket, kolejka i sesje zadań, agenci wykonawczy oraz integracja z procesami Pythona.
- `image-3d-processor.agent.md` — developer przetwarzania obrazu: Python, modele AI, geometria, kalibracja i eksport GLB.

### Weryfikacja

- `tester.agent.md` — tester. Dobiera i uruchamia testy do kryteriów akceptacji, sprawdza istotne kontrakty między komponentami oraz raportuje wyniki i ograniczenia środowiska.

Użytkownik może kontaktować się bezpośrednio z `3D From Video - Project Manager`, wybierając tę rolę w selektorze agentów Copilot. Manager prowadzi zadanie od ustalenia celu przez dobór specjalistów po zebranie wyników. Przy większej zmianie architekt przygotowuje plan, analityk dostarcza udokumentowane porównanie technologii, developerzy implementują swoje części, a tester niezależnie weryfikuje kryteria akceptacji. Przy małych zmianach manager angażuje tylko potrzebną rolę.

## Dokumentacja

- [Dokumentacja architektury i aktualnego przepływu](doc/architecture.md) — przegląd komponentów, przepływu zdjęcia do GLB, kontraktów plikowych, wymagań oraz bieżącego statusu obsługi wideo.
- [Kontrakt API sesji wielozdjęciowej](doc/multiphoto_api.md) — endpointy sesji i klatek, metadane ARCore, status, wersjonowane modele GLB oraz integracja workerów.

## Uruchomienie

W katalogu głównym projektu:

```bash
npm install
npm start
```

To uruchamia główny system, który obserwuje zmiany i inicjuje procesy przetwarzania.

W przypadku uruchamiania usług WebSocket / agentów należy pracować z katalogami:

- system/img3d_ws
- system/img3d_ws_agent

oraz odpowiednimi konfiguracjami środowiskowymi i tokenami.

## Przyszły plan rozwoju

Najważniejszym kierunkiem rozwoju jest przejście z generowania modelu z pojedynczego zdjęcia na generowanie modelu z filmu.

Planowane etapy:

1. wybór klatek z materiału wideo,
2. analiza sekwencji i kalibracja kamery,
3. dopasowanie punktów / geometrii między klatkami,
4. łączenie danych z wielu ujęć w jedną strukturę 3D,
5. poprawa jakości modelu i stabilności pipeline,
6. finalizacja eksportu do GLB z większą dokładnością i lepszą spójnością geometrii.

### Warto zwrócić uwagę

- obecnie projekt jest gotowy do pracy w wersji beta,
- system ma już kompletne elementy do obsługi zdjęć,
- architektura jest przygotowana do rozszerzenia na wideo,
- przyszłe prace koncentrować będą się na sekwencyjnym przetwarzaniu klatek i scalaniu danych 3D.

## Podsumowanie

To repozytorium jest prototypem systemu do generowania modeli 3D z obrazów i filmów. Oprócz legacy generowania GLB z pojedynczego zdjęcia zawiera wielozdjęciowy przepływ sesji z równoległymi workerami i osobnym agentem sumującym. Rozwój przetwarzania bezpośrednio z filmu pozostaje dalszym kierunkiem prac.

## Licencja

Projekt korzysta z licencji określonej w pliku package.json / repozytorium i może być rozwijany dalej w ramach dalszej pracy nad systemem 3D.
