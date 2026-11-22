#include <stdio.h>
#include <string.h>
#include "common.h"
#include "room.h"
#include "logger.h"

int find_room_by_id(int room_id) {
    for (int i = 0; i < MAX_ROOMS; i++) {
        if (rooms[i].is_active && rooms[i].room_id == room_id) {
            return i;
        }
    }

    return -1;
}

int find_room_by_name(const char *room_name) {
    for (int i = 0; i < MAX_ROOMS; i++) {
        if (rooms[i].is_active &&
            strcmp(rooms[i].room_name, room_name) == 0) {
            return i;
        }
    }

    return -1;
}

/* Cap nhat so thanh vien va trang thai phong cua client. */
void remove_client_from_room(int client_index) {
    Client *client = &clients[client_index];

    if (client->current_room_id < 0) {
        return;
    }

    int room_index = find_room_by_id(client->current_room_id);

    if (room_index >= 0 && rooms[room_index].member_count > 0) {
        rooms[room_index].member_count--;
    }

    client->current_room_id = -1;
}

/* Dem phong theo chu so huu, khong theo ket noi hay phong dang tham gia. */
int count_owned_rooms(int user_index) {
    int count = 0;
    for (int i = 0; i < MAX_ROOMS; i++) {
        if (rooms[i].is_active &&
            strcmp(rooms[i].owner, users[user_index].username) == 0) {
            count++;
        }
    }
    return count;
}

void create_room(int client_index, const char *room_name) {
    Client *client = &clients[client_index];

    if (client->user_index < 0) {
        send_message(client->socket_fd, "ERROR Not logged in\n");
        return;
    }

    if (count_owned_rooms(client->user_index) >= MAX_ROOMS_PER_USER) {
        send_message(client->socket_fd, "ERROR Room creation limit reached (maximum 10 rooms)\n");
        return;
    }

    if (find_room_by_name(room_name) >= 0) {
        send_message(client->socket_fd, "ERROR Room already exists\n");
        return;
    }

    int slot = -1;
    for (int i = 0; i < MAX_ROOMS; i++) {
        if (!rooms[i].is_active) {
            slot = i;
            break;
        }
    }

    if (slot < 0) {
        send_message(client->socket_fd, "ERROR Room database is full\n");
        return;
    }

    AuctionRoom *room = &rooms[slot];
    room->room_id = next_room_id++;
    snprintf(room->room_name, sizeof(room->room_name), "%s", room_name);
    snprintf(room->owner, sizeof(room->owner), "%s",
             users[client->user_index].username);
    room->member_count = 0;
    room->is_active = 1;

    log_event("ROOM_CREATED id=%d name=%s owner=%s",
              room->room_id, room->room_name, room->owner);

    char response[128];
    snprintf(response, sizeof(response), "OK ROOM_CREATED ID: %d\n", room->room_id);
    send_message(client->socket_fd, response);
}

void list_rooms(int client_index) {
    int socket_fd = clients[client_index].socket_fd;
    int room_count = 0;

    send_message(socket_fd, "OK ROOM_LIST\n");

    for (int i = 0; i < MAX_ROOMS; i++) {
        if (rooms[i].is_active) {
            char response[160];
            snprintf(response, sizeof(response),
                     "ROOM %d %s OWNER %s MEMBERS %d\n",
                     rooms[i].room_id,
                     rooms[i].room_name,
                     rooms[i].owner,
                     rooms[i].member_count);
            if (send_message(socket_fd, response) < 0) {
                return;
            }
            room_count++;
        }
    }

    if (room_count == 0) {
        send_message(socket_fd, "NO_ROOMS\n");
    }

    send_message(socket_fd, "END_ROOM_LIST\n");
}

void join_room(int client_index, int room_id) {
    Client *client = &clients[client_index];

    if (client->user_index < 0) {
        send_message(client->socket_fd, "ERROR Not logged in\n");
        return;
    }

    if (client->current_room_id >= 0) {
        send_message(client->socket_fd, "ERROR Already in a room\n");
        return;
    }

    int room_index = find_room_by_id(room_id);
    if (room_index < 0) {
        send_message(client->socket_fd, "ERROR Room not found\n");
        return;
    }

    client->current_room_id = room_id;
    rooms[room_index].member_count++;

    log_event("ROOM_JOIN username=%s fd=%d room_id=%d members=%d",
              users[client->user_index].username, client->socket_fd,
              room_id, rooms[room_index].member_count);

    char response[128];
    snprintf(response, sizeof(response), "OK JOINED_ROOM %s\n",
             rooms[room_index].room_name);
    send_message(client->socket_fd, response);
}

void leave_room(int client_index) {
    Client *client = &clients[client_index];

    if (client->user_index < 0) {
        send_message(client->socket_fd, "ERROR Not logged in\n");
        return;
    }

    if (client->current_room_id < 0) {
        send_message(client->socket_fd, "ERROR Not in a room\n");
        return;
    }

    int old_room_id = client->current_room_id;
    const char *username = users[client->user_index].username;
    remove_client_from_room(client_index);
    log_event("ROOM_LEAVE username=%s fd=%d room_id=%d",
              username, client->socket_fd, old_room_id);
    send_message(client->socket_fd, "OK LEFT_ROOM\n");
}
