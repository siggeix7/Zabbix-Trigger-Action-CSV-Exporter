#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import csv
import json
import sys

# =========================
# CONFIGURAZIONE ZABBIX
# =========================
SERVER = "http://127.0.0.1/zabbix"
API_URL = f"{SERVER}/api_jsonrpc.php"

USERNAME = "Admin"
PASSWORD = "zabbix"

# Se usi HTTPS self-signed metti False (ma nel tuo caso sei in http)
VERIFY_SSL = True

# Nome file CSV di output
if len(sys.argv) > 1:
    OUTPUT_CSV = sys.argv[1]
else:
    OUTPUT_CSV = "zabbix_trigger_actions_detailed.csv"


# -------------------------
# Helper per chiamare la API
# -------------------------
def zabbix_api(method, params, auth_token=None, request_id=1):
    """
    Chiamata generica alla Zabbix API.
    Con Zabbix 7.2+ l'autenticazione va nell'header HTTP:
    Authorization: Bearer <token>
    e NON più nel campo 'auth' del JSON.
    """
    headers = {"Content-Type": "application/json-rpc"}
    if auth_token is not None:
        headers["Authorization"] = f"Bearer {auth_token}"

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": request_id,
    }

    resp = requests.post(
        API_URL,
        headers=headers,
        json=payload,
        verify=VERIFY_SSL,
        timeout=30
    )

    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"Zabbix API error: {data['error']}")

    return data["result"]


# -------------------------
# Helper di “traduzione”
# -------------------------
CONDITION_TYPE_MAP = {
    0: "Host group",
    1: "Host",
    2: "Trigger",
    3: "Trigger name",
    4: "Trigger severity",
    5: "Trigger value",
    6: "Time period",
    13: "Host template",
    15: "Application",
    16: "Maintenance status",
}

OPERATOR_MAP = {
    0: "=",
    1: "<>",
    2: "like",
    3: "not like",
    4: "in",
    5: ">=",
    6: "<=",
    7: "not in",
}

SEVERITY_MAP = {
    "0": "Not classified",
    "1": "Information",
    "2": "Warning",
    "3": "Average",
    "4": "High",
    "5": "Disaster",
}

TRIGGER_VALUE_MAP = {
    "0": "OK",
    "1": "PROBLEM",
}

EVENTSOURCE_MAP = {
    "0": "Trigger",
    "1": "Discovery",
    "2": "Auto registration",
    "3": "Internal",
    "4": "Service",
}

STATUS_MAP = {
    "0": "Enabled",
    "1": "Disabled",
}


def build_lookup_maps(actions, auth_token):
    """
    Raccoglie tutti gli ID (hostgroup, host, template, trigger, utenti, gruppi,
    media type) usati nelle condizioni e nelle operations e fa alcune chiamate
    API per recuperarne i nomi.
    """
    hostgroup_ids = set()
    host_ids = set()
    template_ids = set()
    trigger_ids = set()
    user_ids = set()
    usrgrp_ids = set()
    mediatype_ids = set()

    # 1) Raccogli ID da condizioni e operations
    for action in actions:
        flt = action.get("filter") or {}
        conditions = flt.get("conditions", [])

        for c in conditions:
            ctype = int(c.get("conditiontype", -1))
            value = c.get("value")
            if not value:
                continue

            if ctype == 0:       # host group
                hostgroup_ids.add(value)
            elif ctype == 1:     # host
                host_ids.add(value)
            elif ctype == 2:     # trigger
                trigger_ids.add(value)
            elif ctype == 13:    # host template
                template_ids.add(value)

        # operations, recovery, acknowledge
        for op_list_name in ("operations", "recoveryOperations", "acknowledgeOperations"):
            for op in action.get(op_list_name, []):
                for u in op.get("opmessage_user", []):
                    user_ids.add(u.get("userid"))
                for g in op.get("opmessage_usrgrp", []):
                    usrgrp_ids.add(g.get("usrgrpid"))

                m = op.get("opmessage") or {}
                mtid = m.get("mediatypeid")
                if mtid:
                    mediatype_ids.add(mtid)

    # 2) Lookup da API
    def id_map(method, id_field, name_field, ids):
        if not ids:
            return {}
        res = zabbix_api(
            method,
            {"output": [id_field, name_field], id_field + "s": list(ids)},
            auth_token=auth_token,
        )
        return {obj[id_field]: obj[name_field] for obj in res}

    # hostgroup.get
    hostgroups = {}
    if hostgroup_ids:
        res = zabbix_api(
            "hostgroup.get",
            {"output": ["groupid", "name"], "groupids": list(hostgroup_ids)},
            auth_token=auth_token,
        )
        hostgroups = {g["groupid"]: g["name"] for g in res}

    # host.get
    hosts = {}
    if host_ids:
        res = zabbix_api(
            "host.get",
            {"output": ["hostid", "host"], "hostids": list(host_ids)},
            auth_token=auth_token,
        )
        hosts = {h["hostid"]: h["host"] for h in res}

    # template.get
    templates = {}
    if template_ids:
        res = zabbix_api(
            "template.get",
            {"output": ["templateid", "name"], "templateids": list(template_ids)},
            auth_token=auth_token,
        )
        templates = {t["templateid"]: t["name"] for t in res}

    # trigger.get
    triggers = {}
    if trigger_ids:
        res = zabbix_api(
            "trigger.get",
            {"output": ["triggerid", "description"], "triggerids": list(trigger_ids)},
            auth_token=auth_token,
        )
        triggers = {t["triggerid"]: t["description"] for t in res}

    # user.get
    users = {}
    if user_ids:
        res = zabbix_api(
            "user.get",
            {"output": ["userid", "alias", "name", "surname"], "userids": list(user_ids)},
            auth_token=auth_token,
        )
        for u in res:
            full_name = " ".join(x for x in [u.get("name"), u.get("surname")] if x)
            label = f"{u.get('alias') or ''}".strip()
            if full_name:
                label = f"{label} ({full_name})" if label else full_name
            users[u["userid"]] = label or u["userid"]

    # usergroup.get
    usergroups = {}
    if usrgrp_ids:
        res = zabbix_api(
            "usergroup.get",
            {"output": ["usrgrpid", "name"], "usrgrpids": list(usrgrp_ids)},
            auth_token=auth_token,
        )
        usergroups = {g["usrgrpid"]: g["name"] for g in res}

    # mediatype.get
    mediatypes = {}
    if mediatype_ids:
        res = zabbix_api(
            "mediatype.get",
            {"output": ["mediatypeid", "name", "description"], "mediatypeids": list(mediatype_ids)},
            auth_token=auth_token,
        )
        for m in res:
            label = m.get("name") or m.get("description") or m.get("mediatypeid")
            mediatypes[m["mediatypeid"]] = label

    return {
        "hostgroups": hostgroups,
        "hosts": hosts,
        "templates": templates,
        "triggers": triggers,
        "users": users,
        "usergroups": usergroups,
        "mediatypes": mediatypes,
    }


def describe_condition(c, maps):
    ctype = int(c.get("conditiontype", -1))
    op = int(c.get("operator", 0))
    value = c.get("value", "")

    type_label = CONDITION_TYPE_MAP.get(ctype, f"Type {ctype}")
    op_label = OPERATOR_MAP.get(op, str(op))

    # “Traduzioni” di valore in base al tipo
    if ctype == 0:  # Host group
        name = maps["hostgroups"].get(value, value)
        val_label = f"{name} (ID {value})"
    elif ctype == 1:  # Host
        name = maps["hosts"].get(value, value)
        val_label = f"{name} (ID {value})"
    elif ctype == 2:  # Trigger
        name = maps["triggers"].get(value, value)
        val_label = f"{name} (ID {value})"
    elif ctype == 13:  # Template
        name = maps["templates"].get(value, value)
        val_label = f"{name} (ID {value})"
    elif ctype == 4:  # Trigger severity
        val_label = SEVERITY_MAP.get(value, value)
    elif ctype == 5:  # Trigger value
        val_label = TRIGGER_VALUE_MAP.get(value, value)
    else:
        val_label = value

    return f"{type_label} {op_label} {val_label}"


def summarize_operations(ops, maps):
    if not ops:
        return ""

    lines = []
    for op in ops:
        op_type = int(op.get("operationtype", -1))
        step_from = op.get("esc_step_from")
        step_to = op.get("esc_step_to")

        step_part = ""
        if step_from and step_to:
            if step_from == step_to:
                step_part = f"step {step_from}"
            else:
                step_part = f"steps {step_from}-{step_to}"

        msg = op.get("opmessage") or {}
        mtid = msg.get("mediatypeid")
        mt_label = maps["mediatypes"].get(mtid, mtid) if mtid else None
        subject = msg.get("subject") or ""
        message = msg.get("message") or ""

        # Destinatari
        user_labels = [
            maps["users"].get(u.get("userid"), u.get("userid"))
            for u in op.get("opmessage_user", [])
        ]
        grp_labels = [
            maps["usergroups"].get(g.get("usrgrpid"), g.get("usrgrpid"))
            for g in op.get("opmessage_usrgrp", [])
        ]

        targets_parts = []
        if user_labels:
            targets_parts.append("utenti: " + ", ".join(user_labels))
        if grp_labels:
            targets_parts.append("gruppi: " + ", ".join(grp_labels))
        if mt_label:
            targets_parts.append(f"media type: {mt_label}")

        targets_str = "; ".join(targets_parts) if targets_parts else "nessun destinatario"

        if op_type == 0:  # send message
            line = f"[SEND MSG] {step_part} -> {targets_str}"
            if subject:
                line += f" | subject: {subject}"
            if message:
                # taglieremo per non avere muri di testo nel CSV
                short_msg = message.replace("\n", " ")
                if len(short_msg) > 120:
                    short_msg = short_msg[:117] + "..."
                line += f" | msg: {short_msg}"
        else:
            line = f"[OP type {op_type}] {step_part} -> {targets_str}"

        lines.append(line)

    # Un'operazione per riga (il CSV verrà quotato correttamente)
    return "\n".join(lines)


# -------------------------
# MAIN
# -------------------------
def main():
    # 1) Login per ottenere il token
    login_params = {
        "username": USERNAME,   # sulle versioni vecchie sarebbe "user"
        "password": PASSWORD,
    }

    print(f"[*] Login a Zabbix su {API_URL} come {USERNAME}...")
    auth_token = zabbix_api("user.login", login_params)
    print("[+] Login OK.")

    # 2) action.get per trigger actions
    print("[*] Recupero delle trigger actions (eventsource = 0)...")

    action_params = {
        "output": "extend",
        "filter": {"eventsource": "0"},
        "selectOperations": "extend",
        "selectRecoveryOperations": "extend",
        "selectAcknowledgeOperations": "extend",
        "selectFilter": "extend",
    }

    actions = zabbix_api("action.get", action_params, auth_token=auth_token)
    print(f"[+] Trovate {len(actions)} trigger actions.")

    if not actions:
        print("Nessuna trigger action trovata, esco.")
        return

    # 3) Costruisco mappe ID -> nome per host/trigger/utenti/gruppi/mediatype
    print("[*] Costruisco le mappe di lookup (host, gruppi, utenti, mediatype, ...)")
    maps = build_lookup_maps(actions, auth_token)

    # 4) Definisco le colonne del CSV
    fieldnames = [
        "actionid",
        "name",
        "eventsource",
        "eventsource_text",
        "status",
        "status_text",
        "esc_period",
        "def_shortdata",
        "def_longdata",
        "r_shortdata",
        "r_longdata",
        "ack_shortdata",
        "ack_longdata",
        "conditions_human",
        "operations_human",
        "recovery_operations_human",
        "ack_operations_human",
        "filter_raw_json",
        "operations_raw_json",
        "recoveryOperations_raw_json",
        "acknowledgeOperations_raw_json",
    ]

    print(f"[*] Scrivo il CSV in: {OUTPUT_CSV}")

    with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for action in actions:
            row = {}

            # Campi base
            row["actionid"] = action.get("actionid")
            row["name"] = action.get("name")
            row["eventsource"] = action.get("eventsource")
            row["status"] = action.get("status")
            row["esc_period"] = action.get("esc_period")

            row["eventsource_text"] = EVENTSOURCE_MAP.get(
                str(action.get("eventsource")), str(action.get("eventsource"))
            )
            row["status_text"] = STATUS_MAP.get(
                str(action.get("status")), str(action.get("status"))
            )

            # Template messaggi
            row["def_shortdata"] = action.get("def_shortdata")
            row["def_longdata"] = action.get("def_longdata")
            row["r_shortdata"] = action.get("r_shortdata")
            row["r_longdata"] = action.get("r_longdata")
            row["ack_shortdata"] = action.get("ack_shortdata")
            row["ack_longdata"] = action.get("ack_longdata")

            # Condizioni in formato umano
            flt = action.get("filter") or {}
            conditions = flt.get("conditions", []) or []
            cond_strings = [describe_condition(c, maps) for c in conditions]
            row["conditions_human"] = "\n".join(cond_strings)

            # Operations riassunte
            ops = action.get("operations", []) or []
            rec_ops = action.get("recoveryOperations", []) or []
            ack_ops = action.get("acknowledgeOperations", []) or []

            row["operations_human"] = summarize_operations(ops, maps)
            row["recovery_operations_human"] = summarize_operations(rec_ops, maps)
            row["ack_operations_human"] = summarize_operations(ack_ops, maps)

            # JSON grezzi (per avere tutti i dettagli in caso servano)
            row["filter_raw_json"] = json.dumps(flt, ensure_ascii=False)
            row["operations_raw_json"] = json.dumps(ops, ensure_ascii=False)
            row["recoveryOperations_raw_json"] = json.dumps(rec_ops, ensure_ascii=False)
            row["acknowledgeOperations_raw_json"] = json.dumps(ack_ops, ensure_ascii=False)

            writer.writerow(row)

    print("[+] Esportazione completata.")
    print(f"[+] File generato: {OUTPUT_CSV}")

    # 5) Logout (opzionale)
    try:
        zabbix_api("user.logout", [], auth_token=auth_token)
        print("[*] Logout eseguito.")
    except Exception as e:
        print(f"[!] Errore durante il logout (ignorabile): {e}")


if __name__ == "__main__":
    main()
