#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <ctype.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include "common.h"
#include "client_handler.h"
#include "room.h"
#include "logger.h"

/* Noi cap phat bo nho that cho cac bien dung chung. */
Client clients[MAX_CLIENTS];
User users[MAX_USERS];
AuctionRoom rooms[MAX_ROOMS];
int user_count = 0;
int next_room_id = 1;

int send_all(int socket_fd, const char *data, int length) {
    int total = 0;

    while (total < length) {
        int sent = (int)send(socket_fd, data + total,
                             (size_t)(length - total), 0);

        if (sent <= 0) {
            if (sent < 0 && errno == EINTR) {
                continue;
            }
            return -1;
        }

        total += sent;
    }

    return total;
}

int send_message(int socket_fd, const char *message) {
    return send_all(socket_fd, message, (int)strlen(message));
}

static void close_client(int index) {
    if (clients[index].socket_fd >= 0) {
        int user_index = clients[index].user_index;

        /* Neu mat ket noi, tu dong roi phong va dang xuat. */
        const char *username = (user_index >= 0 && user_index < user_count)
                                   ? users[user_index].username : "guest";
        int old_room_id = clients[index].current_room_id;
        log_event("CLIENT_DISCONNECTED fd=%d user=%s room_id=%d",
                  clients[index].socket_fd, username, old_room_id);
        remove_client_from_room(index);

        if (user_index >= 0 && user_index < user_count) {
            users[user_index].is_logged_in = 0;
            users[user_index].client_fd = -1;
        }

        close(clients[index].socket_fd);
        clients[index].socket_fd = -1;
        clients[index].length = 0;
        clients[index].user_index = -1;
        clients[index].current_room_id = -1;
        clients[index].input_state = INPUT_COMMAND;
        memset(clients[index].pending_username, 0, sizeof(clients[index].pending_username));
    }
}

int main(void) {
    int server_fd;
    int option = 1;
    struct sockaddr_in server_address;

    signal(SIGPIPE, SIG_IGN);

    for (int i = 0; i < MAX_CLIENTS; i++) {
        clients[i].socket_fd = -1;
        clients[i].length = 0;
        clients[i].user_index = -1;
        clients[i].current_room_id = -1;
        clients[i].input_state = INPUT_COMMAND;
        clients[i].pending_username[0] = '\0';
    }

    memset(rooms, 0, sizeof(rooms));

    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        perror("socket");
        return 1;
    }

    if (setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &option, sizeof(option)) < 0) {
        perror("setsockopt");
        close(server_fd);
        return 1;
    }

    memset(&server_address, 0, sizeof(server_address));
    server_address.sin_family = AF_INET;
    server_address.sin_addr.s_addr = INADDR_ANY;
    server_address.sin_port = htons(PORT);

    if (bind(server_fd, (struct sockaddr *)&server_address, sizeof(server_address)) < 0) {
        perror("bind");
        close(server_fd);
        return 1;
    }
    
    if (listen(server_fd, 10) < 0) {
        perror("listen");
        close(server_fd);
        return 1;
    }

    printf("Auction server is running on port %d\n", PORT);
    log_event("SERVER_START port=%d", PORT);

    while (1) {
        fd_set read_fds;
        int max_fd = server_fd;

        FD_ZERO(&read_fds);
        FD_SET(server_fd, &read_fds);

        for (int i = 0; i < MAX_CLIENTS; i++) {
            int client_fd = clients[i].socket_fd;
            if (client_fd >= 0) {
                FD_SET(client_fd, &read_fds);
                if (client_fd > max_fd) {
                    max_fd = client_fd;
                }
            }
        }

        int activity = select(max_fd + 1, &read_fds, NULL, NULL, NULL);
        if (activity < 0) {
            if (errno == EINTR) {
                continue;
            }
            perror("select");
            break;
        }

        if (FD_ISSET(server_fd, &read_fds)) {
            int client_fd = accept(server_fd, NULL, NULL);

            if (client_fd >= 0) {
                int added = 0;

                if (client_fd >= FD_SETSIZE) {
                    close(client_fd);
                    continue;
                }

                for (int i = 0; i < MAX_CLIENTS; i++) {
                    if (clients[i].socket_fd < 0) {
                        clients[i].socket_fd = client_fd;
                        clients[i].length = 0;
                        clients[i].user_index = -1;
                        clients[i].current_room_id = -1;
                        clients[i].input_state = INPUT_COMMAND;
                        clients[i].pending_username[0] = '\0';

                        send_message(client_fd,
                                     "OK Connected to auction server\n");
                        added = 1;
                        printf("Client connected: %d\n", client_fd);
                        log_event("CLIENT_CONNECTED fd=%d", client_fd);
                        break;
                    }
                }

                if (!added) {
                    send_message(client_fd, "ERROR Server is full\n");
                    close(client_fd);
                }
            }
        }

        for (int i = 0; i < MAX_CLIENTS; i++) {
            int client_fd = clients[i].socket_fd;

            if (client_fd < 0 || !FD_ISSET(client_fd, &read_fds)) {
                continue;
            }

            char incoming[BUFFER_SIZE];
            int received = (int)recv(client_fd, incoming, sizeof(incoming), 0);

            if (received <= 0) {
                printf("Client disconnected: %d\n", client_fd);
                close_client(i);
                continue;
            }

            for (int j = 0; j < received; j++) {
                char ch = incoming[j];

                if (ch == '\n') {
                    clients[i].buffer[clients[i].length] = '\0';
                    /* Chi QUIT dung cu phap o che do lenh moi dong ket noi. */
                    char *line = clients[i].buffer;
                    while (isspace((unsigned char)*line)) {
                        line++;
                    }
                    int should_close = clients[i].input_state == INPUT_COMMAND &&
                        strncmp(line, "QUIT", 4) == 0 &&
                        strspn(line + 4, " \t\r\v\f") == strlen(line + 4);
                    handle_command(i, clients[i].buffer);
                    memset(clients[i].buffer, 0, sizeof(clients[i].buffer));

                    clients[i].length = 0;

                    if (should_close) {
                        close_client(i);
                        break;
                    }
                }
                else if (clients[i].length < BUFFER_SIZE - 1) {
                    clients[i].buffer[clients[i].length++] = ch;
                }
                else {
                    send_message(client_fd, "ERROR Command too long\n");
                    close_client(i);
                    break;
                }
            }
        }
    }

    for (int i = 0; i < MAX_CLIENTS; i++) {
        close_client(i);
    }

    log_event("SERVER_STOP");
    close(server_fd);
    return 0;
}
