#ifndef USER_H
#define USER_H

int find_user(const char *username);
void register_user(int client_index, const char *username, const char *password);
void login_user(int client_index, const char *username, const char *password);
void logout_user(int client_index);

#endif
