# System architecture

Four views:

1. **Whole system**: every component, who owns it, and how data flows.
2. **Emergency request**: who does what, in order, during a 1 a.m. request.
3. **Evening pre-alert**: topping hospitals up before the night's emergencies.
4. **Zoom: ranking engine**: what happens inside one `rank_sources()` call ([spec](../RANKING_ENGINE_SPEC.md)).

Owners: **FS1** Full-stack 1 · **FS2** Full-stack 2 · **DS1** Data scientist 1 · **DS2** Data scientist 2 · **FE** Frontend.

## 1. Whole system

```mermaid
flowchart TB
    subgraph PEOPLE["People"]
        direction LR
        LAB(["Hospital lab worker"])
        CLIN(["Clinician"])
        SITE(["Supplying site staff<br/>regional centre or hospital"])
        CENTRE(["Regional centre staff<br/>evening top-ups"])
        EXPERT(["Expert reviewers"])
    end

    subgraph CLIENTS["Clients"]
        direction LR
        WEB["Web screens · FE<br/>request entry · options list<br/>confirmation · pre-alert list"]
        PHONE["Basic phone<br/>SMS"]
        GW["SMS gateway"]
        RTAB["Results tab · FE"]
    end

    subgraph BACKEND["Backend · Python · FastAPI"]
        direction LR
        SMSP["SMS parser · FS2<br/>text to structured request"]
        API["HTTP API · FS1"]
        WF["Workflow · FS1<br/>request, pick, confirm, dispatch<br/>confirm timeout: next site"]
        AUDIT[("Audit log · FS1")]
        FB["Fallback mode · FS1<br/>tool down: phone process"]
    end

    subgraph ENGINE["Decision engine · deterministic, no LLM numbers"]
        direction LR
        RANK["Ranking · DS1<br/>compatible spare units<br/>above safety stock<br/>template reasons"]
        ARR["Arrival ranges<br/>p10 · p50 · p90"]
        PRE["Evening pre-alert · DS2<br/>hospitals out of common groups"]
        REP["Replay · DS2<br/>rerun last year's requests"]
    end

    subgraph STORE["Data and settings"]
        direction LR
        CSV["Starter CSVs · synthetic<br/>DATA_DIR · git-ignored"]
        ING["Ingest · FS2"]
        DB[("SQLite")]
        CFG["Country settings · FS2<br/>lending rules · safety stock<br/>arrival params · demo clock"]
        RJ[("results/*.json")]
    end

    LAB --> WEB
    LAB --> PHONE
    CLIN -- "reads advice" --> WEB
    SITE -- "confirms shelf, dispatches" --> WEB
    CENTRE --> WEB
    EXPERT --> RTAB

    PHONE <--> GW <--> SMSP
    SMSP --> API
    WEB <--> API
    API --> WF
    WF --> AUDIT
    WF -.-> FB

    WF -- "rank request" --> RANK
    RANK <--> ARR
    API -- "evening run" --> PRE
    REP -- "calls in a loop" --> RANK

    CSV --> ING --> DB
    DB --> RANK
    DB --> ARR
    DB --> PRE
    DB --> REP
    CFG -.-> ENGINE
    CFG -.-> WF
    REP --> RJ --> RTAB
```

## 2. Emergency request

```mermaid
sequenceDiagram
    autonumber
    actor Lab as Lab worker
    participant API as API and workflow
    participant Eng as Ranking engine
    actor Site as Supplying site
    participant Log as Audit log

    Lab->>API: Request by web or SMS
    API->>Log: record request
    API->>Eng: rank_sources
    Eng-->>API: ranked options with ranges and reasons, plus baseline
    alt advice is set
        API-->>Lab: wait too long, consider emergency group O or patient transfer
    end
    API-->>Lab: options, model and baseline side by side
    Lab->>API: pick, change or reject
    API->>Log: record decision
    API->>Site: confirm units are on the shelf
    alt confirmed in time
        Site->>API: confirm, then dispatch
        API->>Log: record confirm and dispatch
        API-->>Lab: dispatched, arrival window
    else timeout or not on shelf
        API->>Log: record timeout
        API-->>Lab: move to next option
    end
    Note over Lab,Site: The engine suggests, people decide. A qualified person crossmatches and releases every unit. If the tool is down, everyone falls back to phone calls.
```

## 3. Evening pre-alert

```mermaid
flowchart LR
    CLOCK["Evening<br/>demo clock or real time"] --> CHECK["Pre-alert · DS2<br/>yesterday's closing stock<br/>per hospital and blood group"]
    CHECK --> LIST["List of hospitals out of<br/>the most common group"]
    LIST --> STAFF(["Regional centre staff<br/>review the list"])
    STAFF --> TOPUP["Top-up delivery<br/>sent that evening"]
    TOPUP --> FEWER["Fewer 1 a.m.<br/>emergency requests"]
```

## 4. Zoom: ranking engine, one `rank_sources()` call

```mermaid
flowchart TB
    REQ["Request<br/>facility_id · patient_group · units_needed · requested_at"]

    REQ --> COMPAT["compat.py · fixed lookup table<br/>patient group to acceptable unit groups<br/>unknown: O- and O+ only + flag"]
    REQ --> ASOF["as_of = request date minus 1 day<br/>yesterday's closing count"]

    COMPAT --> CAND
    ASOF --> CAND
    CAND["Candidates<br/>every facility except requester and SAT-* satellites<br/>centres only if sharing_allowed is false"]

    CAND --> STOCK["stock.py · per candidate<br/>centre: spare = all compatible RBC + WB<br/>hospital: spare = stock minus max of usual_level and min_keep<br/>O- never below o_neg_reserve<br/>near_expiry, capped at spare"]

    STOCK --> ETA["eta.py · Monte Carlo, fixed seed<br/>arrival = wait + extra + ratio x travel_hours<br/>p10 · p50 · p90<br/>no model file: fallback, model_used false"]

    ETA --> SORT["rank.py · sort<br/>1. p50 in quarter-hour buckets<br/>2. near_expiry, most first<br/>3. backup power first<br/>4. spare, most first"]

    SORT --> FULL{"Any candidate with<br/>spare >= units_needed?"}
    FULL -- yes --> TOP["Top N options"]
    FULL -- no --> PART["Best partial options<br/>flag partial · advice no_full_source"]

    TOP --> ADV{"Top option p90<br/>over clinician_limit_h?"}
    PART --> OUT
    ADV -- yes --> ADV2["advice: consider_emergency_O_or_transfer"] --> OUT
    ADV -- no --> OUT

    REQ --> BASE["Baseline mode · today's rule, also the fallback<br/>supply centre if it has enough,<br/>else 2 nearest regional centres by road_km<br/>quote = map time + 2 h, no range"]
    BASE --> OUT

    OUT["reasons.py · string templates filled with computed numbers<br/>JSON: options + baseline + notes + flags"]
```

## Safety principles and where they live

| Principle | Where |
|---|---|
| A person makes every decision; the tool suggests | Workflow: pick, confirm, dispatch are human steps |
| The tool never decides blood group; unknown group means group O only | Ranking (`compat.py`) |
| Compatibility is a fixed lookup table, never a model | Ranking (`compat.py`) |
| Every time estimate has a range (p10 / p50 / p90) | Arrival ranges |
| No LLM produces any number; reasons are templates | Ranking (`reasons.py`) |
| A hospital lends only what it can spare; O- reserve is protected | Ranking (`stock.py`) + country settings |
| Stock is yesterday's count until the supplying site confirms | Workflow confirm step + `stock_note` |
| Every action is recorded | Audit log |
| If the tool fails, everyone falls back to the phone process | Fallback mode |
| A new country is a new settings file, no code change | Country settings |
| No patient identifier is collected; the engine stores only the request fields it uses | Ranking (`load.py`); see [DATA_PROTECTION.md](../DATA_PROTECTION.md) |
