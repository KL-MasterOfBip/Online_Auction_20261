#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <ctype.h>
#include "common.h"
#include "client_handler.h"
#include "user.h"
#include "room.h"
#include "logger.h"

static int split_tokens(char *command, char *tokens[], int max_tokens) {
    int count = 0;
    char *p = command;

    while (*p != '\0') {
        while (*p != '\0' && isspace((unsigned char)*p)) {
            p++;
        }

        if (*p == '\0') {
            break;
        }

        if (count >= max_tokens) {
            return max_tokens + 1;
        }

        tokens[count++] = p;

        while (*p != '\0' && !isspace((unsigned char)*p)) {
            p++;
        }

        if (*p != '\0') {
            *p = '\0';
            p++;
        }
    }

    return count;
}

/* Username va password khong chua khoang trang, giong giao thuc lenh cu. */
static int valid_auth_input(const char *text, size_t limit) {
    size_t length = strlen(text);
    if (length == 0 || length >= limit) {
        return 0;
    }
    for (size_t i = 0; i < length; i++) {
        if (isspace((unsigned char)text[i])) {
            return 0;
        }
    }
    return 1;
}

/* Moi client co buoc nhap rieng; khong cho mot client chan cac client khac. */
static void handle_auth_input(int client_index, const char *input) {
    Client *client = &clients[client_index];
    int socket_fd = client->socket_fd;
    InputState state = client->input_state;
    int registering = state == REGISTER_USERNAME || state == REGISTER_PASSWORD;

    if (state == REGISTER_USERNAME || state == LOGIN_USERNAME) {
        if (!valid_auth_input(input, USERNAME_SIZE)) {
            send_message(socket_fd, "ERROR Username must be 1-31 characters without whitespace\n");
            send_message(socket_fd, registering ? "New username:\n" : "Username:\n");
            return;
        }
        if (registering && find_user(input) >= 0) {
            send_message(socket_fd, "ERROR Username already exists\n");
            send_message(socket_fd, "New username:\n");
            return;
        }
        snprintf(client->pending_username, sizeof(client->pending_username), "%s", input);
        client->input_state = registering ? REGISTER_PASSWORD : LOGIN_PASSWORD;
        send_message(socket_fd, registering ? "New password:\n" : "Password:\n");
        return;
    }

    if (!valid_auth_input(input, PASSWORD_SIZE)) {
        send_message(socket_fd, "ERROR Password must be 1-63 characters without whitespace\n");
        send_message(socket_fd, registering ? "New password:\n" : "Password:\n");
        return;
    }

    /* Client khac co the vua dang ky ten nay trong luc cho nhap password. */
    if (registering && find_user(client->pending_username) >= 0) {
        client->pending_username[0] = '\0';
        client->input_state = REGISTER_USERNAME;
        send_message(socket_fd, "ERROR Username already exists\n");
        send_message(socket_fd, "New username:\n");
        return;
    }

    client->input_state = INPUT_COMMAND;
    if (registering) {
        register_user(client_index, client->pending_username, input);
    }
    else {
        login_user(client_index, client->pending_username, input);
    }
    memset(client->pending_username, 0, sizeof(client->pending_username));
}

/* ID phong phai la so nguyen duong trong pham vi int. */
static int parse_room_id(const char *input) {
    char *end = NULL;
    errno = 0;
    long room_id = strtol(input, &end, 10);
    if (errno != 0 || input[0] == '\0' || *end != '\0' ||
        room_id <= 0 || room_id > 2147483647L) {
        return -1;
    }
    return (int)room_id;
}

/* Giu buoc nhap hien tai neu ten phong hoac ID chua hop le. */
static void handle_room_input(int client_index, const char *input) {
    Client *client = &clients[client_index];
    int socket_fd = client->socket_fd;

    if (client->input_state == CREATE_ROOM_NAME) {
        if (!valid_auth_input(input, ROOM_NAME_SIZE)) {
            send_message(socket_fd, "ERROR Room name must be 1-49 characters without whitespace\n");
            send_message(socket_fd, "Room name:\n");
            return;
        }
        if (find_room_by_name(input) >= 0) {
            send_message(socket_fd, "ERROR Room already exists\n");
            send_message(socket_fd, "Room name:\n");
            return;
        }
        client->input_state = INPUT_COMMAND;
        create_room(client_index, input);
    }
    else {
        int room_id = parse_room_id(input);
        if (room_id < 0) {
            send_message(socket_fd, "ERROR Invalid room ID\n");
            send_message(socket_fd, "Room ID:\n");
            return;
        }
        if (find_room_by_id(room_id) < 0) {
            send_message(socket_fd, "ERROR Room not found\n");
            send_message(socket_fd, "Room ID:\n");
            return;
        }
        client->input_state = INPUT_COMMAND;
        join_room(client_index, room_id);
    }
}

void handle_command(int client_index, char *command) {
    int socket_fd = clients[client_index].socket_fd;
    char *tokens[4];
    char response[RESPONSE_SIZE];

    command[strcspn(command, "\r\n")] = '\0';

    if (clients[client_index].input_state == CREATE_ROOM_NAME ||
        clients[client_index].input_state == JOIN_ROOM_ID) {
        handle_room_input(client_index, command);
        return;
    }
    if (clients[client_index].input_state != INPUT_COMMAND) {
        handle_auth_input(client_index, command);
        return;
    }

    int count = split_tokens(command, tokens, 4);

    if (count == 0) {
        send_message(socket_fd, "ERROR Empty command\n");
        return;
    }

    /* Chi ghi ten lenh, khong ghi username/password trong luong hoi dap. */
    log_event("COMMAND_RECEIVED fd=%d command=%s", socket_fd, tokens[0]);

    if ((strcmp(tokens[0], "REGISTER") == 0 ||
         strcmp(tokens[0], "LOGIN") == 0) && count == 1) {
        int registering = strcmp(tokens[0], "REGISTER") == 0;
        if (clients[client_index].user_index >= 0) {
            send_message(socket_fd, registering
                         ? "ERROR Cannot register while logged in\n"
                         : "ERROR Already logged in\n");
            return;
        }
        if (registering && user_count >= MAX_USERS) {
            send_message(socket_fd, "ERROR User database is full\n");
            return;
        }
        clients[client_index].input_state = registering ? REGISTER_USERNAME : LOGIN_USERNAME;
        send_message(socket_fd, registering ? "New username:\n" : "Username:\n");
    }
    else if (strcmp(tokens[0], "PING") == 0 && count == 1) {
        send_message(socket_fd, "OK PONG\n");
    }
    else if (strcmp(tokens[0], "HELP") == 0 && count == 1) {
        send_message(socket_fd,
            "OK Commands: HELP, PING, REGISTER, LOGIN, LOGOUT, "
            "CREATE_ROOM, LIST_ROOMS, JOIN_ROOM, LEAVE_ROOM, QUIT\n");
    }
    else if (strcmp(tokens[0], "REGISTER") == 0 && count == 3) {
        size_t username_length = strlen(tokens[1]);
        size_t password_length = strlen(tokens[2]);

        if (username_length == 0 || username_length >= USERNAME_SIZE ||
            password_length == 0 || password_length >= PASSWORD_SIZE) {
            send_message(socket_fd,
                         "ERROR Username or password is too long or too short\n");
            return;
        }

        register_user(client_index, tokens[1], tokens[2]);
    }
    else if (strcmp(tokens[0], "LOGIN") == 0 && count == 3) {
        size_t username_length = strlen(tokens[1]);
        size_t password_length = strlen(tokens[2]);

        if (username_length == 0 || username_length >= USERNAME_SIZE ||
            password_length == 0 || password_length >= PASSWORD_SIZE) {
            send_message(socket_fd,
                         "ERROR Username or password is too long or too short\n");
            return;
        }

        login_user(client_index, tokens[1], tokens[2]);
    }
    else if (strcmp(tokens[0], "LOGOUT") == 0 && count == 1) {
        logout_user(client_index);
    }
    else if ((strcmp(tokens[0], "CREATE_ROOM") == 0 ||
              strcmp(tokens[0], "JOIN_ROOM") == 0) && count == 1) {
        Client *client = &clients[client_index];
        int creating = strcmp(tokens[0], "CREATE_ROOM") == 0;
        if (client->user_index < 0) {
            send_message(socket_fd, "ERROR Not logged in\n");
            return;
        }
        if (creating && count_owned_rooms(client->user_index) >= MAX_ROOMS_PER_USER) {
            send_message(socket_fd, "ERROR Room creation limit reached (maximum 10 rooms)\n");
            return;
        }
        if (!creating && client->current_room_id >= 0) {
            send_message(socket_fd, "ERROR Already in a room\n");
            return;
        }
        client->input_state = creating ? CREATE_ROOM_NAME : JOIN_ROOM_ID;
        send_message(socket_fd, creating ? "Room name:\n" : "Room ID:\n");
    }
    else if (strcmp(tokens[0], "CREATE_ROOM") == 0 && count == 2) {
        if (strlen(tokens[1]) >= ROOM_NAME_SIZE) {
            send_message(socket_fd, "ERROR Room name is too long\n");
            return;
        }
        create_room(client_index, tokens[1]);
    }
    else if (strcmp(tokens[0], "LIST_ROOMS") == 0 && count == 1) {
        list_rooms(client_index);
    }
    else if (strcmp(tokens[0], "JOIN_ROOM") == 0 && count == 2) {
        int room_id = parse_room_id(tokens[1]);
        if (room_id < 0) {
            send_message(socket_fd, "ERROR Invalid room ID\n");
            return;
        }

        join_room(client_index, (int)room_id);
    }
    else if (strcmp(tokens[0], "LEAVE_ROOM") == 0 && count == 1) {
        leave_room(client_index);
    }
    else if (strcmp(tokens[0], "QUIT") == 0 && count == 1) {
        send_message(socket_fd, "OK Goodbye\n");
    }
    else if (strcmp(tokens[0], "PING") == 0 ||
             strcmp(tokens[0], "HELP") == 0 ||
             strcmp(tokens[0], "REGISTER") == 0 ||
             strcmp(tokens[0], "LOGIN") == 0 ||
             strcmp(tokens[0], "LOGOUT") == 0 ||
             strcmp(tokens[0], "CREATE_ROOM") == 0 ||
             strcmp(tokens[0], "LIST_ROOMS") == 0 ||
             strcmp(tokens[0], "JOIN_ROOM") == 0 ||
             strcmp(tokens[0], "LEAVE_ROOM") == 0 ||
             strcmp(tokens[0], "QUIT") == 0) {
        send_message(socket_fd, "ERROR Invalid command or arguments\n");
    }
    else {
        log_event("UNKNOWN_COMMAND fd=%d command=%s", socket_fd, tokens[0]);
        snprintf(response, sizeof(response),
                 "ERROR Unknown command: %s\n", tokens[0]);
        send_message(socket_fd, response);
    }
}
