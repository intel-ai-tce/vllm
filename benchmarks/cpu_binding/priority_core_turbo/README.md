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
2. Check wether PCT is enabled or not and get the CPU ids list with PCT.

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


3. Set CPU ids based on power domain to use PCT feature if CPU ids list hasn't set.

    ```bash
   docker compose --profile set up --abort-on-container-exit
    ```
4. (Optional) Debug with intel-speed-select tool directly

    ```bash
   docker compose run --rm intel-speed-select-shell
    ```

