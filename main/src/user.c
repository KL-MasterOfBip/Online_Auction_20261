#include <stdio.h>
#include <string.h>
#include "common.h"
#include "user.h"
#include "room.h"
#include "logger.h"

int find_user(const char *username) {
    for (int i = 0; i < user_count; i++) {
        if (strcmp(users[i].username, username) == 0) {
            return i;
        }
    }

    return -1;
}

void register_user(int client_index,
                   const char *username,
                   const char *password) {
    Client *client = &clients[client_index];
    int socket_fd = client->socket_fd;

    /* Chi guest moi duoc dang ky tai khoan. */
    if (client->user_index >= 0) {
        send_message(socket_fd, "ERROR Cannot register while logged in\n");
        return;
    }

    if (find_user(username) >= 0) {
        send_message(socket_fd, "ERROR Username already exists\n");
        return;
    }

    if (user_count >= MAX_USERS) {
        send_message(socket_fd, "ERROR User database is full\n");
        return;
    }

    User *user = &users[user_count];
    snprintf(user->username, sizeof(user->username), "%s", username);
    snprintf(user->password, sizeof(user->password), "%s", password);
    user->is_logged_in = 0;
    user->client_fd = -1;
    user_count++;

    log_event("REGISTER_SUCCESS username=%s", username);
    send_message(socket_fd, "OK Account registered\n");
}

void login_user(int client_index, const char *username, const char *password) {
    Client *client = &clients[client_index];

    if (client->user_index >= 0) {
        send_message(client->socket_fd, "ERROR Already logged in\n");
        return;
    }

    int index = find_user(username);

    if (index < 0 || strcmp(users[index].password, password) != 0) {
        send_message(client->socket_fd,
                     "ERROR Invalid username or password\n");
        return;
    }

    if (users[index].is_logged_in) {
        send_message(client->socket_fd,
                     "ERROR Account already logged in\n");
        return;
    }

    users[index].is_logged_in = 1;
    users[index].client_fd = client->socket_fd;
    client->user_index = index;

    log_event("LOGIN_SUCCESS username=%s fd=%d", username, client->socket_fd);
    send_message(client->socket_fd, "OK Login successful\n");
}

void logout_user(int client_index) {
    Client *client = &clients[client_index];

    if (client->user_index < 0) {
        send_message(client->socket_fd, "ERROR Not logged in\n");
        return;
    }

    /* Dang xuat dong thoi roi khoi phong neu dang tham gia. */
    const char *username = users[client->user_index].username;
    int old_room_id = client->current_room_id;
    remove_client_from_room(client_index);
    log_event("LOGOUT username=%s fd=%d previous_room=%d",
              username, client->socket_fd, old_room_id);

    int index = client->user_index;

    if (index < user_count) {
        users[index].is_logged_in = 0;
        users[index].client_fd = -1;
    }

    client->user_index = -1;
    send_message(client->socket_fd, "OK Logout successful\n");
}
