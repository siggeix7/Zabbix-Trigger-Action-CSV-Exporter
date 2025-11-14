# Zabbix-Trigger-Action-CSV-Exporter

## Esportazione delle **Trigger Actions** da Zabbix in CSV

Questo script Python utilizza le API JSON-RPC di **Zabbix** (senza libreria esterna) per esportare in un file CSV tutte le **Trigger Actions** (azioni con `eventsource = 0`), includendo sia campi “base” sia informazioni più leggibili su condizioni e operazioni.

### Cosa fa lo script

1. **Login a Zabbix**

   * Esegue una chiamata `user.login` verso
     `http://127.0.0.1/zabbix/api_jsonrpc.php`
   * Ottiene un token e lo usa tramite header HTTP
     `Authorization: Bearer <token>` (compatibile con Zabbix 7.2+).

2. **Recupero delle Trigger Actions**

   * Usa il metodo `action.get` con:

     * `eventsource = 0` → solo azioni di tipo *Trigger*
     * `selectOperations`, `selectRecoveryOperations`, `selectAcknowledgeOperations`, `selectFilter` impostati su `"extend"` per avere tutti i dettagli.

3. **Lookup di nomi e descrizioni**

   Per rendere il CSV più leggibile, lo script raccoglie tutti gli ID usati nelle condizioni/operazioni e li traduce in nomi “umani” tramite ulteriori chiamate API:

   * `hostgroup.get` → nomi dei gruppi host
   * `host.get` → nomi degli host
   * `template.get` → nomi dei template
   * `trigger.get` → descrizioni dei trigger
   * `user.get` → utenti destinatari (alias + nome)
   * `usergroup.get` → gruppi di utenti
   * `mediatype.get` → nomi dei media type (es. Email, SMS…)

4. **Costruzione di campi leggibili**

   Nel CSV crea, tra gli altri, questi campi:

   * `eventsource_text`, `status_text` → versione testuale di `eventsource` e `status`
   * `conditions_human` → elenco delle condizioni in forma umana, es:

     * `Host group = Linux servers (ID 23)`
     * `Trigger severity >= High`
     * `Trigger value = PROBLEM`
   * `operations_human`, `recovery_operations_human`, `ack_operations_human` → riassunto delle operazioni:

     * destinatari (utenti / gruppi)
     * media type
     * subject
     * un estratto del messaggio
     * eventuali step (es. “steps 1–3”)

5. **Salvataggio su CSV**

   * Scrive tutte le azioni in un file CSV (di default:
     `zabbix_trigger_actions_detailed.csv`)
   * Include anche i campi JSON grezzi:

     * `filter_raw_json`
     * `operations_raw_json`
     * `recoveryOperations_raw_json`
     * `acknowledgeOperations_raw_json`
       così hai sempre la struttura completa in caso servano dettagli aggiuntivi.

6. **Logout**

   * Alla fine prova a chiamare `user.logout` (opzionale) per chiudere la sessione.

---

### Come eseguire lo script

1. **Prerequisiti**

   * Python 3 installato (es. `python3`).
   * Modulo `requests` installato:

     ```bash
     pip install requests
     ```
   * Accesso API al tuo Zabbix (utente e password o, se modifichi lo script, un API token).

2. **Configurazione**

   All’inizio dello script trovi queste variabili:

   ```python
   SERVER = "http://10.77.71.40/zabbix"
   USERNAME = "Admin"
   PASSWORD = "zabbix"
   ```

   Modificale se necessario (indirizzo del server, utente, password).

3. **Rendere lo script eseguibile (opzionale ma comodo)**

   Supponendo che il file si chiami `Trigger_Action_CSV_Exporter_detailed.py`:

   ```bash
   chmod +x Trigger_Action_CSV_Exporter_detailed.py
   ```

4. **Esecuzione**

   * Con il nome di file CSV di default:

     ```bash
     ./Trigger_Action_CSV_Exporter_detailed.py
     ```

   * Oppure specificando il nome del CSV in output:

     ```bash
     ./Trigger_Action_CSV_Exporter_detailed.py trigger_actions_dettagliate.csv
     ```

5. **Risultato**

   Alla fine troverai il file CSV nella stessa cartella dello script, ad esempio:

   ```text
   zabbix_trigger_actions_detailed.csv
   ```

   Aprendolo (con Excel, LibreOffice Calc, ecc.) vedrai:

   * una riga per ogni Trigger Action;
   * colonne con info base, condizioni leggibili, operazioni, template di messaggi;
   * JSON grezzi per ulteriori analisi.
