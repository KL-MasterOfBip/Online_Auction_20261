#ifndef ROOM_H
#define ROOM_H

int find_room_by_id(int room_id);
int find_room_by_name(const char *room_name);
void remove_client_from_room(int client_index);
int count_owned_rooms(int user_index);
void create_room(int client_index, const char *room_name);
void list_rooms(int client_index);
void join_room(int client_index, int room_id);
void leave_room(int client_index);

#endif
