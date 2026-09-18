# Image 3D WebSocket Service

Usługa Node.js odpowiedzialna za komunikację pomiędzy aplikacją PHP a agentami wykonującymi przetwarzanie **Image → 3D**.

## 1. Architektura

```text
                    INTERNET
                       │
                       │ HTTPS / WSS :443
                       ▼
                ┌───────────────┐
                │    Apache2    │
                │   TLS / SSL   │
                └───────┬───────┘
                        │
                        │ WebSocket proxy
                        │ ws://127.0.0.1:8443
                        ▼
                ┌───────────────┐
                │    Node.js    │
                │ img3d-ws      │
                └───────┬───────┘
                        │
             ┌──────────┴──────────┐
             │                     │
             ▼                     ▼
          data/                 agents
             │
             ├── sessionId/
             │   ├── photo.jpg
             │   ├── state.json
             │   └── model.glb
             │
             └── systemStatus.json
```

Apache odpowiada za:

* HTTPS,
* certyfikat domeny,
* WSS,
* publiczny dostęp do WebSocket.

Node.js odpowiada za:

* obserwowanie katalogu `data`,
* wykrywanie nowych zdjęć,
* przydzielanie zadań agentom,
* autoryzację agentów,
* przesyłanie zdjęć,
* odbieranie postępu,
* odbieranie plików GLB,
* aktualizowanie `state.json`.

Node.js **nie potrzebuje własnego certyfikatu TLS**.

---

# 2. Wymagania

Serwer:

* Linux,
* systemd,
* Node.js,
* npm,
* Apache2,
* moduły Apache:

  * `proxy`
  * `proxy_http`
  * `proxy_wstunnel`
  * `ssl`
  * `headers`

Opcjonalnie:

* `openssl` — do automatycznego generowania tokenów agentów.

Sprawdzenie:

```bash
node --version
npm --version
apache2 -v
systemctl --version
```

---

# 3. Struktura katalogów

Przykładowo:

```text
/opt/img3d-ws/
├── server.js
├── install.sh
├── package.json
├── package-lock.json
├── node_modules/
├── .env
└── agents.json

/var/www/html/data/
├── systemStatus.json
└── 0123456789abcdef0123456789abcdef/
    ├── photo.jpg
    ├── state.json
    └── model.glb
```

`install.sh` i `server.js` powinny znajdować się w tym samym katalogu.

---

# 4. Instalacja Node.js

Jeżeli Node.js nie jest jeszcze zainstalowany, należy go zainstalować przed uruchomieniem instalatora.

Sprawdzenie:

```bash
node --version
npm --version
```

Instalator nie instaluje Node.js automatycznie.

---

# 5. Instalacja usługi

Umieść:

```text
install.sh
server.js
```

w jednym katalogu.

Nadaj instalatorowi prawa wykonywania:

```bash
chmod +x install.sh
```

Uruchom:

```bash
sudo ./install.sh
```

---

# 6. Pytania instalatora

Instalator poprosi między innymi o:

## Katalog `data`

Przykład:

```text
/var/www/html/data
```

Jeżeli proponowana wartość jest poprawna, wystarczy nacisnąć Enter.

---

## Port Node.js

Domyślnie:

```text
8443
```

Node będzie nasłuchiwał wyłącznie na:

```text
127.0.0.1:8443
```

Port ten **nie powinien być wystawiony bezpośrednio do Internetu**.

---

## Użytkownik usługi

Domyślnie:

```text
www-data
```

Użytkownik musi istnieć w systemie.

---

## ID pierwszego agenta

Przykład:

```text
agent-01
```

---

## Token agenta

Można wpisać własny token albo nacisnąć Enter.

Wtedy instalator wygeneruje losowy token.

Przykładowo:

```text
9d4f2c...a81e
```

Token należy przekazać agentowi.

---

# 7. Plik `.env`

Instalator utworzy:

```text
/opt/img3d-ws/.env
```

Przykład:

```env
DATA_DIR=/var/www/html/data
PORT=8443
AGENTS_FILE=/opt/img3d-ws/agents.json
```

Plik powinien mieć prawa:

```text
600
```

---

# 8. Lista agentów

Autoryzowani agenci znajdują się w:

```text
/opt/img3d-ws/agents.json
```

Przykład:

```json
{
    "agents": {
        "agent-01": {
            "token": "TOKEN_AGENT_01"
        },
        "agent-02": {
            "token": "TOKEN_AGENT_02"
        }
    }
}
```

Każdy agent ma:

* unikalny `agentId`,
* własny token.

Nie należy używać tego samego tokenu dla wielu agentów.

---

# 9. Dodawanie kolejnego agenta

Edytuj:

```bash
sudo nano /opt/img3d-ws/agents.json
```

Dodaj:

```json
{
    "agents": {
        "agent-01": {
            "token": "TOKEN_AGENT_01"
        },
        "agent-02": {
            "token": "TOKEN_AGENT_02"
        }
    }
}
```

Następnie można przeładować konfigurację bez pełnego restartu:

```bash
sudo systemctl reload-or-restart img3d-ws
```

albo wysłać:

```bash
sudo systemctl kill -s HUP img3d-ws
```

Serwer obsługuje `SIGHUP` i ponownie odczytuje `agents.json`.

---

# 10. Usługa systemd

Instalator tworzy:

```text
/etc/systemd/system/img3d-ws.service
```

Usługa uruchamia się automatycznie podczas startu systemu.

Sprawdzenie:

```bash
sudo systemctl status img3d-ws
```

Restart:

```bash
sudo systemctl restart img3d-ws
```

Zatrzymanie:

```bash
sudo systemctl stop img3d-ws
```

Włączenie przy starcie:

```bash
sudo systemctl enable img3d-ws
```

Wyłączenie automatycznego startu:

```bash
sudo systemctl disable img3d-ws
```

---

# 11. Logi

Bieżące logi:

```bash
sudo journalctl -u img3d-ws -f
```

Ostatnie 100 wpisów:

```bash
sudo journalctl -u img3d-ws -n 100 --no-pager
```

Logi z aktualnego uruchomienia:

```bash
sudo journalctl -u img3d-ws -b
```

---

# 12. Apache2

## 12.1 Wymagane moduły

Włącz:

```bash
sudo a2enmod proxy
sudo a2enmod proxy_http
sudo a2enmod proxy_wstunnel
sudo a2enmod ssl
sudo a2enmod headers
```

Następnie:

```bash
sudo systemctl restart apache2
```

Sprawdzenie:

```bash
apache2ctl -M | grep -E 'proxy|ssl|wstunnel'
```

---

# 13. VirtualHost HTTPS

Załóżmy, że domena to:

```text
example.com
```

a aplikacja PHP znajduje się w:

```text
/var/www/html
```

Przykładowy VirtualHost:

```apache
<VirtualHost *:443>

    ServerName example.com

    DocumentRoot /var/www/html

    SSLEngine on

    SSLCertificateFile /ścieżka/do/ssl.cert
    SSLCertificateKeyFile /ścieżka/do/ssl.key
    SSLCertificateChainFile /ścieżka/do/ssl.ca

    <Directory /var/www/html>
        AllowOverride All
        Require all granted
    </Directory>

    # ==========================================
    # WebSocket -> Node.js
    # ==========================================

    ProxyPass        "/ws" "ws://127.0.0.1:8123/"
    ProxyPassReverse "/ws" "ws://127.0.0.1:8123/"

</VirtualHost>
```

Po tej konfiguracji:

```text
wss://example.com/ws
```

będzie przekazywane do:

```text
ws://127.0.0.1:8443/
```

---

# 14. Jeżeli Apache już ma skonfigurowany SSL

Jeżeli istniejący VirtualHost wygląda np.:

```apache
<VirtualHost *:443>

    ServerName example.com

    DocumentRoot /var/www/html

    SSLEngine on

    SSLCertificateFile ...
    SSLCertificateKeyFile ...
    SSLCertificateChainFile ...

</VirtualHost>
```

nie trzeba tworzyć drugiego VirtualHosta.

Wystarczy dodać do istniejącego:

```apache
ProxyPass        "/ws" "ws://127.0.0.1:8443/"
ProxyPassReverse "/ws" "ws://127.0.0.1:8443/"

lub

ProxyPass /ws ws://127.0.0.1:8443/
ProxyPassReverse /ws ws://127.0.0.1:8443/
```

---

# 15. Ważne — certyfikaty

Jeżeli obecny Apache korzysta z plików:

```text
ssl.everything
ssl.combined
ssl.ca
ssl.key
ssl.cert
```

Node.js nie musi mieć do nich dostępu.

Apache pozostaje właścicielem konfiguracji TLS.

Schemat:

```text
                 TLS
Internet ──────────────────> Apache
                               │
                               │ WSS
                               ▼
                         Node.js :8443
```

Node otrzymuje już zwykłe połączenie WebSocket:

```text
ws://127.0.0.1:8443
```

Klient natomiast cały czas korzysta z:

```text
wss://example.com/ws
```

Klucz prywatny `ssl.key` pozostaje po stronie Apache.

---

# 16. Test konfiguracji Apache

Przed restartem:

```bash
sudo apache2ctl configtest
```

Poprawny wynik:

```text
Syntax OK
```

Dopiero wtedy:

```bash
sudo systemctl reload apache2
```

---

# 17. Test Node.js bez Apache

Najpierw sprawdź, czy Node nasłuchuje:

```bash
sudo ss -lntp | grep 8443
```

Powinno być podobne do:

```text
LISTEN 0 511 127.0.0.1:8443
```

Jeżeli pojawia się:

```text
0.0.0.0:8443
```

oznacza to, że Node nasłuchuje również na interfejsach zewnętrznych.

W obecnej konfiguracji powinien nasłuchiwać tylko:

```text
127.0.0.1
```

---

# 18. Test WSS

Po skonfigurowaniu Apache agent powinien łączyć się z:

```text
wss://example.com/ws
```

Nie:

```text
ws://example.com:8443
```

i nie:

```text
wss://example.com:8443
```

Port `8443` jest lokalnym portem Node.

---

# 19. Autoryzacja agenta

Po nawiązaniu połączenia agent wysyła:

```json
{
    "type": "auth",
    "agentId": "agent-01",
    "token": "TOKEN_AGENT_01"
}
```

Poprawna odpowiedź serwera:

```json
{
    "type": "auth_ok",
    "agentId": "agent-01"
}
```

Nieprawidłowy token powoduje zamknięcie połączenia.

---

# 20. Przepływ zadania

Po przesłaniu zdjęcia przez PHP:

```text
oczekiwanie
      ↓
uploaded
      ↓
processing
      ↓
ready
```

Node wykrywa:

```text
data/{sessionId}/photo.jpg
```

i szuka wolnego agenta.

Po znalezieniu agenta wysyła najpierw:

```json
{
    "type": "job",
    "jobId": "....",
    "sessionId": "....",
    "filename": "photo.jpg",
    "size": 4839201
}
```

Następnie wysyła zdjęcie jako binarną ramkę WebSocket.

---

# 21. Raportowanie postępu przez agenta

Agent może wysłać:

```json
{
    "type": "progress",
    "jobId": "....",
    "progress": 37
}
```

Node zapisze:

```json
{
    "status": "processing",
    "progress": 37,
    "jobId": "...."
}
```

---

# 22. Przesłanie GLB

Po zakończeniu generowania modelu agent wysyła:

```json
{
    "type": "ready_for_glb",
    "jobId": "...."
}
```

a następnie binarną ramkę zawierającą GLB.

Node sprawdza nagłówek:

```text
glTF
```

i zapisuje:

```text
data/{sessionId}/model.glb
```

Następnie:

```json
{
    "status": "ready",
    "progress": 100,
    "glb": "model.glb"
}
```

---

# 23. Rozłączenie agenta

Jeżeli agent rozłączy się podczas przetwarzania:

```text
processing
     ↓
agent disconnect
     ↓
uploaded
```

Zadanie wraca do kolejki.

Po pojawieniu się dostępnego agenta może zostać wykonane ponownie.

---

# 24. Wielu agentów

Można mieć jednocześnie:

```text
agent-01
agent-02
agent-03
...
```

Node utrzymuje listę połączonych agentów.

Jeżeli jeden agent wykonuje zadanie:

```text
agent-01 → BUSY
agent-02 → IDLE
agent-03 → IDLE
```

kolejne zadanie może zostać przydzielone innemu agentowi.

---

# 25. Bezpieczeństwo

## Node

Node powinien nasłuchiwać wyłącznie:

```text
127.0.0.1:8443
```

Nie należy otwierać portu `8443` w firewallu dla Internetu.

## Tokeny

`agents.json` zawiera sekrety.

Powinien mieć:

```bash
chmod 600 agents.json
```

## Certyfikat

Certyfikat TLS i klucz prywatny pozostają po stronie Apache.

Node nie potrzebuje dostępu do:

```text
ssl.key
```

## data

Katalog:

```text
data/
```

powinien być zabezpieczony przed bezpośrednim dostępem HTTP.

Jeżeli `data` znajduje się pod `DocumentRoot`, należy zablokować jego bezpośrednie udostępnianie.

Przykładowo `.htaccess`:

```apache
Options -Indexes

<Files "*">
    Require all denied
</Files>
```

Jeżeli konfiguracja Apache na danym hostingu nie obsługuje `Require all denied`, należy zastosować odpowiednią konfigurację `<Directory>` w VirtualHost.

---

# 26. Firewall

Nie trzeba otwierać:

```text
8443/tcp
```

dla Internetu.

Publicznie dostępny pozostaje:

```text
443/tcp
```

czyli:

```text
Internet
   │
   └── 443 → Apache → 127.0.0.1:8443 → Node
```

---

# 27. Najczęstsze problemy

## Node nie uruchamia się

Sprawdź:

```bash
sudo systemctl status img3d-ws
```

oraz:

```bash
sudo journalctl -u img3d-ws -n 100 --no-pager
```

---

## Port 8443 jest zajęty

```bash
sudo ss -lntp | grep 8443
```

Można zmienić port w:

```text
.env
```

np.:

```env
PORT=8450
```

Następnie należy również zmienić:

```apache
ProxyPass        "/ws" "ws://127.0.0.1:8450/"
ProxyPassReverse "/ws" "ws://127.0.0.1:8450/"
```

i zrestartować usługę:

```bash
sudo systemctl restart img3d-ws
sudo systemctl reload apache2
```

---

## Apache zwraca 502/503 dla WebSocket

Sprawdź, czy Node działa:

```bash
sudo systemctl status img3d-ws
```

oraz:

```bash
sudo ss -lntp | grep 8443
```

Sprawdź również moduły:

```bash
apache2ctl -M | grep proxy
```

---

## Agent nie może się połączyć

Sprawdź:

```bash
sudo journalctl -u img3d-ws -f
```

Najczęściej problemem jest:

* nieprawidłowy `agentId`,
* nieprawidłowy token,
* nieprawidłowy adres WSS,
* brak `proxy_wstunnel`,
* błędna konfiguracja VirtualHost.

---

# 28. Aktualizacja server.js

Po zmianie:

```text
server.js
```

uruchom:

```bash
sudo systemctl restart img3d-ws
```

Nie trzeba ponownie uruchamiać instalatora.

---

# 29. Aktualizacja agents.json

Po zmianie:

```text
agents.json
```

można wykonać:

```bash
sudo systemctl kill -s HUP img3d-ws
```

Node ponownie odczyta listę agentów.

---

# 30. Podsumowanie

Docelowa konfiguracja:

```text
                         INTERNET
                            │
                            │ HTTPS / WSS
                            │ :443
                            ▼
                    ┌───────────────┐
                    │    Apache2    │
                    │               │
                    │ TLS           │
                    │ SSL           │
                    │ WebSocket     │
                    │ proxy         │
                    └───────┬───────┘
                            │
                            │ ws://127.0.0.1:8443
                            ▼
                    ┌───────────────┐
                    │    Node.js    │
                    │   img3d-ws    │
                    └───────┬───────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
       ┌──────────────┐            ┌──────────────┐
       │    data/     │            │    agents    │
       │              │            │              │
       │ photo        │            │ agent-01     │
       │ state.json   │            │ agent-02     │
       │ model.glb    │            │ agent-03     │
       └──────────────┘            └──────────────┘
```

Klient/agent łączy się tylko z:

```text
wss://example.com/ws
```

Apache zajmuje się TLS, a Node zajmuje się logiką WebSocket i kolejką zadań.
