#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdarg.h>
#include <time.h>
#include "logger.h"

#define LOG_FILE "auction_server.log"

/* Ghi log co timestamp; tuyet doi khong ghi password vao file log. */
void log_event(const char *format, ...) {
    FILE *log_file = fopen(LOG_FILE, "a");
    if (log_file == NULL) {
        perror("Cannot open log file");
        return;
    }

    time_t now = time(NULL);
    struct tm time_info;
    char timestamp[32] = "unknown-time";

    if (localtime_r(&now, &time_info) != NULL) {
        strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S",
                 &time_info);
    }

    fprintf(log_file, "[%s] ", timestamp);

    va_list args;
    va_start(args, format);
    vfprintf(log_file, format, args);
    va_end(args);

    fputc('\n', log_file);
    fclose(log_file);
}
