# Enabling Priority Core Turbo (PCT) to improve vLLM Performance for GPUs

PCT allows for dynamic prioritization of high-priority cores, enabling them to run at higher turbo frequencies. 
In parallel, lower-priority cores operate at base frequency, ensuring optimal distribution of CPU resources. 
This capability is critical for AI workloads that demand sequential or serial processing, 
feeding GPUs faster and improving overall system efficiency 

The Xeon processors currently validated for this setup are: Intel Xeon 6960P and Intel Xeon PLATINUM 8568Y+.

1. Build a docker image for needed software packages.

    ```bash
    docker compose build --no-cache
    ```
2. Check wether PCT is enabled or not and get the CLOS0 CPU ids list with PCT.

    ```bash
    docker compose --profile check up --abort-on-container-exit
    ```
    Example results when PCT is enabled successfully.
    ```bash
    ------------------------------------------------------------
    CPU and Intel Speed Select Capability
    ------------------------------------------------------------
    Intel(R) SST-PP (feature perf-profile) is supported
    Intel(R) SST-TF (feature turbo-freq) is supported
    Intel(R) SST-BF (feature base-freq) is not supported
    Intel(R) SST-CP (feature core-power) is supported
    Intel(R) Speed Select Technology
    Executing on CPU model:173[0xad]
    
    ------------------------------------------------------------
    PCT (Turbo-Frequency) Feature Status
    ------------------------------------------------------------
    ✅ PCT (Turbo-Frequency) data present.
    
    ------------------------------------------------------------
    Core Power (CLOS) Feature Status
    ------------------------------------------------------------
    ✅ Core Power feature ENABLED
    ✅ CLOS ENABLED
    
    ------------------------------------------------------------
    CPU list for TARGET_CLOS=0
    ------------------------------------------------------------
    clos:0 CPU list: 0-7,32-39,64-71,96-103,128-135,160-167,192-199,224-231
    
    ------------------------------------------------------------
    Summary
    ------------------------------------------------------------
    ✅ PCT turbo tables detected (turbo-freq reports high-priority data)
    ✅ Core Power enabled
    ✅ CLOS enabled
    ```


3. Set CPU ids based on power domain to use PCT feature if CLOS0 CPU ids list hasn't set.

    ```bash
   docker compose --profile set up --abort-on-container-exit
    ```

    Example results when PCT is set successfully based on power-domains.
    ```bash
    intel-speed-select-set-1  | ------------------------------------------------------------
    intel-speed-select-set-1  | Config
    intel-speed-select-set-1  | ------------------------------------------------------------
    intel-speed-select-set-1  | HP_PER_DOMAIN=8 (HP_BUCKET=0)
    intel-speed-select-set-1  | INCLUDE_HT=0
    intel-speed-select-set-1  | HP_CLOS=0  OTHER_CLOS=2
    intel-speed-select-set-1  | DEBUG_MODE=0  DRY_RUN=0  DEBUG_VERBOSE=0  DEBUG_MAP=0
    intel-speed-select-set-1  | 
    intel-speed-select-set-1  | ------------------------------------------------------------
    intel-speed-select-set-1  | HP selection per NUMA node (initial pick)
    intel-speed-select-set-1  | ------------------------------------------------------------
    intel-speed-select-set-1  | node 0 -> 0 1 2 3 4 5 6 7
    intel-speed-select-set-1  | node 1 -> 32 33 34 35 36 37 38 39
    intel-speed-select-set-1  | node 2 -> 64 65 66 67 68 69 70 71
    intel-speed-select-set-1  | node 3 -> 96 97 98 99 100 101 102 103
    intel-speed-select-set-1  | 
    intel-speed-select-set-1  | HP initial ranges      : 0-7,32-39,64-71,96-103
    intel-speed-select-set-1  | HP effective (with HT) : 0-7,32-39,64-71,96-103,128-135,160-167,192-199,224-231
    intel-speed-select-set-1  | 
    intel-speed-select-set-1  | ------------------------------------------------------------
    intel-speed-select-set-1  | Computed CPU lists
    intel-speed-select-set-1  | ------------------------------------------------------------
    intel-speed-select-set-1  | HP (effective) : 0-7,32-39,64-71,96-103,128-135,160-167,192-199,224-231
    intel-speed-select-set-1  | Non-HP         : 8-31,40-63,72-95,104-127,136-159,168-191,200-223,232-255
    intel-speed-select-set-1  | 
    intel-speed-select-set-1  | ------------------------------------------------------------
    intel-speed-select-set-1  | Apply CLOS assignments (quiet)
    intel-speed-select-set-1  | ------------------------------------------------------------
    intel-speed-select-set-1  | Setting HP -> CLOS0, Non-HP -> CLOS2
    intel-speed-select-set-1  | Applied.
    intel-speed-select-set-1  | 
    intel-speed-select-set-1  | ------------------------------------------------------------
    intel-speed-select-set-1  | Verification (concise CPU->CLOS)
    intel-speed-select-set-1  | ------------------------------------------------------------
    intel-speed-select-set-1  | HP list should be clos:0
    intel-speed-select-set-1  | cpu-0 clos:0
    intel-speed-select-set-1  | … (showing first 40 lines)
    intel-speed-select-set-1  | 
    intel-speed-select-set-1  | Non-HP list should be clos:2
    intel-speed-select-set-1  | cpu-8 clos:2
    intel-speed-select-set-1  | … (showing first 40 lines)
    intel-speed-select-set-1  | 
    intel-speed-select-set-1  | Done.
    intel-speed-select-set-1 exited with code 0
    ```
    
4. (Optional) Debug with intel-speed-select tool directly

    ```bash
   docker compose run --rm intel-speed-select-shell
    ```

