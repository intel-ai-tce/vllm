docker compose build --no-cache
#docker compose --profile check up 
docker compose --profile check up --abort-on-container-exit
docker compose --profile set up --abort-on-container-exit


[Shell]
docker compose run --rm intel-speed-select-shell



sudo cpupower frequency-set -g performance
sudo x86_energy_perf_policy performance
