# Zadanie: Przebudowa strony projektu Image → 3D

Przeprojektuj istniejącą stronę internetową projektu **Image → 3D** w nowoczesną, profesjonalną i responsywną stronę typu landing page, prezentującą projekt, jego działanie, możliwości i plany rozwoju.

## 1. Strony referencyjne

Obecna aplikacja:
index.php


Potraktuj stronę referencyjną jako inspirację dla profesjonalnej prezentacji produktu. Nie kopiuj jej dosłownie. Stwórz własny, współczesny projekt wizualny odpowiedni dla systemu przetwarzania obrazów i generowania geometrii 3D.

## 2. Najważniejszy cel

Obecna funkcjonalność aplikacji ma stać się jednym z bloków nowej strony głównej, a nie całą zawartością strony.

Strona powinna przedstawiać projekt jako rozwijany system technologiczny. Użytkownik powinien najpierw zrozumieć, czym jest Image → 3D, zobaczyć jego potencjał, poznać sposób użycia, a następnie przejść do właściwego narzędzia.

Nie usuwaj istniejącej funkcjonalności i nie twórz wyłącznie statycznego projektu graficznego.

## 3. Wygląd i styl

Zaprojektuj nowoczesny interfejs o wysokiej jakości wizualnej, kojarzący się z profesjonalnym oprogramowaniem 3D, computer vision i sztuczną inteligencją.

Wymagania:

* elegancki, minimalistyczny, techniczny wygląd;
* czytelna typografia i wyraźna hierarchia nagłówków;
* przemyślana paleta kolorów, kontrast i duża ilość wolnej przestrzeni;
* subtelne gradienty, delikatne obramowania i nowoczesne powierzchnie kart;
* duże sekcje wizualne przełamujące monotonię tekstu;
* płynne animacje, mikrointerakcje i efekty pojawiania się elementów podczas przewijania;
* estetyczne przyciski z wyraźnymi stanami hover, focus i active;
* spójne ikony i ilustracje techniczne;
* pełna responsywność na komputerach, tabletach i telefonach.

Unikaj wyglądu typowego szablonu administracyjnego, przesadnego użycia kart, przypadkowych dekoracji i nadmiernej liczby animacji.

Strona ma wyglądać jak rzeczywisty produkt technologiczny, a nie prezentacja szkolna.

## 4. Układ strony głównej

### A. Nawigacja

Utwórz nowoczesny pasek nawigacyjny, najlepiej przyklejony do górnej krawędzi podczas przewijania.

Powinien zawierać:

* logo lub typograficzny znak Image → 3D;
* link „O projekcie”;
* link „Jak to działa”;
* link „Zastosowania”;
* link „Rozwój”;
* przełącznik języka PL / EN;
* wyróżniony przycisk „Wypróbuj aplikację”.

Linki do poszczególnych sekcji powinny przewijać stronę do odpowiednich miejsc. Zastosuj płynne przewijanie z uwzględnieniem wysokości przyklejonej nawigacji.

Na telefonach zastosuj wygodne menu mobilne.

### B. Sekcja otwierająca — Hero

Zaprojektuj duży, efektowny blok otwierający stronę.

Proponowany nagłówek:

„Od zdjęcia do geometrii 3D”

Proponowany opis:

„Eksperymentalny system wykorzystujący analizę obrazu do odtwarzania uproszczonej geometrii elementów architektury na podstawie fotografii.”

Dodaj dwa przyciski:

* „Wypróbuj aplikację” — prowadzi do bloku aplikacji.
* „Poznaj technologię” — prowadzi do sekcji opisującej działanie systemu.

Po prawej stronie lub w tle umieść dużą, atrakcyjną wizualizację pokazującą ideę przekształcania fotografii budynku w uproszczony model 3D.

Wizualizacja może przedstawiać fotografię architektury, wyodrębnione płaszczyzny, geometryczną rekonstrukcję budynku i gotowy model 3D. Zastosuj delikatne animacje, ale zachowaj czytelność treści.

Nie przedstawiaj ilustracji koncepcyjnej jako rzeczywistego wyniku działania algorytmu.

### C. Sekcja „O projekcie”

Przedstaw ideę Image → 3D.

Wyjaśnij, że celem projektu jest automatyczne rozpoznawanie dominujących płaszczyzn architektonicznych na zdjęciu i budowanie na ich podstawie lekkiego modelu geometrycznego.

Podkreśl:

* analizę pojedynczych fotografii;
* wykrywanie głównych powierzchni architektury;
* pomijanie nieregularnych elementów, które utrudniają uproszczoną rekonstrukcję;
* generowanie geometrii zamiast ograniczania wyniku do chmury punktów;
* możliwość eksportowania wynikowego modelu do formatu GLB.

Nie obiecuj dokładności, wydajności ani funkcji, których nie potwierdza istniejąca implementacja.

Zaprojektuj sekcję z tekstem i ilustracją techniczną rozmieszczonymi obok siebie.

### D. Sekcja „Jak to działa”

Przedstaw proces w postaci kilku czytelnych etapów z ilustracjami i krótkimi opisami.

1. **Zdjęcie wejściowe** — użytkownik dostarcza fotografię.
2. **Analiza obrazu** — system szuka dominujących płaszczyzn i cech geometrycznych.
3. **Budowa geometrii** — na podstawie rozpoznanych powierzchni powstaje uproszczony model.
4. **Eksport modelu** — wynik można pobrać jako plik GLB, jeśli przetwarzanie zakończyło się poprawnie.

Wizualnie przedstaw kolejne etapy za pomocą ilustracji, miniatur, kart lub animowanej prezentacji. Na małych ekranach układ ma przechodzić do jednej kolumny.

### E. Sekcja aplikacji — „Wypróbuj Image → 3D”

To kluczowa część strony. Zachowaj tutaj istniejącą aplikację i jej funkcjonalność.

Umieść ją w dużym, wyraźnie wydzielonym panelu, który wygląda jak część profesjonalnego narzędzia, a nie zwykły formularz.

Panel powinien zachować:

* wczytywanie zdjęcia z urządzenia;
* podgląd wybranego zdjęcia;
* rozpoczynanie nowej sesji;
* wyświetlanie identyfikatora sesji i czasu utworzenia, jeśli są dostępne;
* prezentowanie bieżącego statusu i procentowego postępu;
* wyświetlanie podglądu modelu 3D, jeśli istniejąca aplikacja go udostępnia;
* pobieranie modelu GLB po zakończeniu przetwarzania.

Wykorzystaj istniejące elementy HTML, identyfikatory, obsługę zdarzeń, mechanizmy sesji, endpointy, zapytania AJAX i logikę backendu. Przed modyfikacją sprawdź, w jaki sposób te elementy współpracują.

Możesz zmienić ich strukturę HTML i CSS, jeśli nie naruszy to istniejącego działania. W razie potrzeby popraw JavaScript, zachowując kompatybilność z backendem.

Nie zastępuj działającego systemu przykładowym formularzem, atrapą postępu ani fikcyjnym podglądem wyniku.

Zadbaj o prawidłowe stany interfejsu:

* oczekiwanie na zdjęcie;
* przesyłanie pliku;
* przetwarzanie;
* zakończenie z wynikiem;
* błąd przetwarzania.

Przyciski muszą mieć odpowiednie odstępy. Używaj `gap` w kontenerach zamiast dodawania marginesów bezpośrednio do przycisków. Interfejs ma działać prawidłowo także na wąskich ekranach.

Jeśli aktualny adres zawiera parametr `sessionId`, zachowaj prawidłową obsługę istniejącej sesji. Nie usuwaj ani nie resetuj sesji automatycznie podczas wejścia na stronę główną.

### F. Sekcja „Możliwości i zastosowania”

Przedstaw przykładowe zastosowania technologii, takie jak:

* tworzenie uproszczonych modeli budynków;
* prototypowanie geometrii architektonicznej;
* przygotowywanie lekkich zasobów 3D do aplikacji internetowych;
* eksperymenty z rekonstrukcją scen na podstawie obrazów.

Oddziel wyraźnie obecne możliwości systemu od potencjalnych zastosowań, które wymagają dalszego rozwoju.

Wykorzystaj atrakcyjne ilustracje, wizualizacje 3D i układ naprzemiennych bloków tekstowo-graficznych.

### G. Sekcja „Plany rozwoju”

Utwórz atrakcyjną sekcję przedstawiającą kierunki rozwoju projektu.

Możliwe tematy:

* poprawa jakości wykrywania płaszczyzn;
* lepsza obsługa złożonych elementów architektonicznych;
* rozwój rekonstrukcji geometrii;
* poprawa jakości tekstur;
* przetwarzanie większej liczby zdjęć;
* rozwój eksportu i zastosowań modeli w środowiskach 3D.

Przedstaw je jako kierunki planowanego rozwoju, a nie funkcje już dostępne.

Nie wymyślaj dat wdrożeń, wskaźników postępu ani deklaracji o już ukończonych funkcjach.

### H. Sekcja końcowa — wezwanie do działania

Zaprojektuj wyraźny blok końcowy zachęcający do wypróbowania aplikacji.

Nagłówek:
„Zacznij od zdjęcia”

Opis:
„Sprawdź, jak fotografia może posłużyć jako punkt wyjścia do budowy uproszczonego modelu 3D.”

Przycisk:
„Przejdź do aplikacji”

Przycisk powinien przewijać stronę do panelu aplikacji.

### I. Stopka

Dodaj estetyczną stopkę z:

* nazwą Image → 3D;
* krótkim opisem projektu;
* linkami do głównych sekcji strony;
* przełącznikiem języka lub linkami językowymi;
* miejscem na informacje o autorze i ewentualnym repozytorium projektu, jeśli odpowiednie dane są dostępne.

Nie wymyślaj profili społecznościowych ani nieistniejących odnośników.

## 5. Grafiki i animacje

Zaplanuj dedykowane miejsca na:

* fotografię architektoniczną;
* wizualizację wykrytych płaszczyzn;
* uproszczony model geometryczny budynku;
* porównanie zdjęcia wejściowego z modelem;
* ilustracje przedstawiające proces przetwarzania;
* podgląd przestrzeni 3D.

Preferuj rzeczywiste grafiki projektu, jeśli są dostępne. Jeśli ich brakuje, przygotuj spójne zasoby wizualne lub estetyczne miejsca na późniejsze wstawienie grafik.

Nie pozostawiaj pustych, dużych prostokątów bez projektu wizualnego.

Animacje powinny obejmować subtelne pojawianie się sekcji podczas przewijania, efekty hover na elementach interaktywnych i delikatne animacje wybranej wizualizacji 3D.

Zachowaj dobrą wydajność, ogranicz liczbę ciężkich animacji i respektuj ustawienie `prefers-reduced-motion`.

## 6. Nawigacja wewnętrzna i podlinkowane podtytuły

Strona powinna mieć wyraźną strukturę sekcji oraz kilka poziomów nawigacji.

Wykorzystaj:

* linki w górnym menu;
* przyciski CTA prowadzące do aplikacji;
* linki wprowadzające do konkretnych sekcji;
* klikalne odnośniki w wybranych blokach informacyjnych;
* unikalne identyfikatory sekcji HTML;
* aktywne stany nawigacji, jeśli można je wdrożyć bez zbędnej komplikacji.

Każdy link ma prowadzić do istniejącej sekcji lub rzeczywistego zasobu. Nie twórz martwych linków.

## 7. Responsywność i dostępność

Strona musi poprawnie działać na:

* dużych monitorach;
* standardowych laptopach;
* tabletach;
* telefonach w orientacji pionowej i poziomej.

Nie dopuszczaj do poziomego przewijania całej strony, nakładania się tekstów, obcinania przycisków ani zbyt małych obszarów dotykowych.

Na telefonach:

* sekcje wielokolumnowe powinny układać się pionowo;
* przyciski powinny zachowywać odpowiednie odstępy;
* grafiki powinny skalować się proporcjonalnie;
* nawigacja powinna przechodzić do menu mobilnego;
* najważniejsza funkcjonalność aplikacji powinna pozostawać łatwo dostępna.

Zadbaj o semantyczny HTML, widoczne stany fokusu, kontrast tekstu i obsługę klawiaturą.

## 8. Wymagania techniczne

Przed rozpoczęciem pracy przeanalizuj istniejący kod, strukturę plików, CSS, JavaScript i mechanizmy backendu.

Nie zakładaj z góry, że możesz dowolnie zmieniać stos technologiczny. Dopasuj rozwiązanie do istniejącej aplikacji PHP i jej obecnych zależności.

W szczególności:

* zachowaj istniejące mechanizmy sesji i przetwarzania zdjęć;
* zachowaj zgodność z parametrem `lang`;
* nie usuwaj istniejącej obsługi języka polskiego i angielskiego;
* zachowaj dotychczasowe identyfikatory elementów, jeśli korzysta z nich JavaScript;
* nie zmieniaj endpointów bez uzasadnionej konieczności;
* nie usuwaj istniejących funkcji backendu;
* nie wprowadzaj niepotrzebnych bibliotek ani ciężkich frameworków;
* oddzielaj style strony promocyjnej od stylów właściwej aplikacji, aby uniknąć konfliktów CSS;
* stosuj czytelne nazwy klas z odpowiednimi prefiksami;
* unikaj globalnych reguł CSS, które mogłyby zmienić działanie istniejących elementów;
* zachowaj bezpieczeństwo i dotychczasową walidację danych.

Jeżeli potrzebujesz nowych grafik, ikon lub bibliotek, dobierz je do projektu i uzasadnij ich użycie w końcowym podsumowaniu.

## 9. Kryteria odbioru

Pracę uznaj za zakończoną dopiero wtedy, gdy:

1. Strona ma kompletny, nowoczesny układ z wszystkimi opisanymi sekcjami.
2. Obecna aplikacja jest częścią strony głównej i można do niej przejść z menu oraz przycisków CTA.
3. Istniejące wczytywanie zdjęć, sesje, postęp i pobieranie GLB nadal działają.
4. Nawigacja wewnętrzna prowadzi do prawidłowych sekcji.
5. Język polski i angielski nadal działają.
6. Układ poprawnie reaguje na zmianę szerokości ekranu.
7. Animacje są płynne i nie utrudniają korzystania ze strony.
8. Nie ma atrap funkcjonalności, martwych linków ani fikcyjnych informacji o możliwościach systemu.
9. Kod jest uporządkowany i nie wprowadza niepotrzebnych zależności.
10. Zmiany zostały sprawdzone pod kątem błędów JavaScript, PHP i regresji istniejącej funkcjonalności.

## 10. Sposób realizacji

Najpierw przeanalizuj istniejącą aplikację i zidentyfikuj elementy, których działania nie wolno naruszyć.

Następnie przygotuj i wdroż kompletny projekt nowej strony, zamiast ograniczać się do opisu koncepcji lub fragmentów kodu.

Po wdrożeniu sprawdź podstawowe scenariusze działania, w tym wczytanie zdjęcia, uruchomienie nowej sesji, aktualizację statusu, wyświetlenie wyniku i pobranie modelu GLB.

Na końcu przedstaw krótkie podsumowanie zmienionych plików, nowych zależności oraz przeprowadzonych testów.
