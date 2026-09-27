#!/usr/bin/env bash

activity_reporter_start_postgres() {
    local container_name="activity-reporter-postgres"
    local volume_name="activity-reporter-postgres-data"
    local port="${POSTGRES_PORT:-55432}"

    if ! command -v docker >/dev/null 2>&1; then
        echo "Docker is required to start PostgreSQL." >&2
        return 1
    fi

    if docker container inspect "$container_name" >/dev/null 2>&1; then
        if [[ "$(docker inspect --format '{{.State.Running}}' "$container_name")" != "true" ]]; then
            docker start "$container_name" >/dev/null
        fi
    else
        docker run \
            --name "$container_name" \
            --env POSTGRES_USER=activity_reporter \
            --env POSTGRES_PASSWORD=activity_reporter \
            --env POSTGRES_DB=activity_reporter \
            --publish "127.0.0.1:${port}:5432" \
            --volume "${volume_name}:/var/lib/postgresql/data" \
            --detach \
            postgres:17-alpine >/dev/null
    fi

    local attempt
    for attempt in {1..30}; do
        if docker exec "$container_name" \
            pg_isready --username activity_reporter --dbname activity_reporter \
            >/dev/null 2>&1; then
            local actual_port
            actual_port="$(docker inspect --format '{{with (index .NetworkSettings.Ports "5432/tcp")}}{{(index . 0).HostPort}}{{end}}' "$container_name")"
            if [[ -z "$actual_port" ]]; then
                echo "The PostgreSQL container does not publish port 5432." >&2
                return 1
            fi
            export DATABASE_URL="postgresql+psycopg://activity_reporter:activity_reporter@127.0.0.1:${actual_port}/activity_reporter"
            echo "PostgreSQL is ready on 127.0.0.1:${actual_port}."
            echo "DATABASE_URL is exported in the current shell."
            return 0
        fi
        sleep 1
    done

    echo "PostgreSQL did not become ready within 30 seconds." >&2
    return 1
}

activity_reporter_start_postgres
activity_reporter_status=$?
unset -f activity_reporter_start_postgres
if [[ $activity_reporter_status -ne 0 ]]; then
    return "$activity_reporter_status" 2>/dev/null || exit "$activity_reporter_status"
fi
unset activity_reporter_status
