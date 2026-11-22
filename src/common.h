#ifndef COMMON_H
#define COMMON_H

#include <sys/select.h>

#ifndef PORT
#define PORT 8080
#endif

#define MAX_CLIENTS FD_SETSIZE
#define BUFFER_SIZE 1024
#define RESPONSE_SIZE 2048

#define MAX_USERS 100
#define USERNAME_SIZE 32
#define PASSWORD_SIZE 64

#define MAX_ROOMS 100
#define MAX_ROOMS_PER_USER 10
#define ROOM_NAME_SIZE 50

#define MAX_ITEMS 500
#define MAX_ITEMS_PER_ROOM 20
#define ITEM_NAME_SIZE 50
#define MAX_PRICE 1000000000000LL
#define MIN_BID_INCREMENT 10000LL

typedef enum {
    INPUT_COMMAND,
    REGISTER_USERNAME,
    REGISTER_PASSWORD,
    LOGIN_USERNAME,
    LOGIN_PASSWORD,
    CREATE_ROOM_NAME,
    JOIN_ROOM_ID,
    ADD_ITEM_ROOM_ID,
    ADD_ITEM_NAME,
    ADD_ITEM_START_PRICE,
    ADD_ITEM_BUY_NOW_PRICE
} InputState;

typedef struct {
    int socket_fd;
    char buffer[BUFFER_SIZE];
    int length;
    int user_index;       /* -1: client chua dang nhap */
    int current_room_id;  /* -1: client chua tham gia phong nao */
    InputState input_state;
    char pending_username[USERNAME_SIZE];
    int pending_room_id;
    char pending_item_name[ITEM_NAME_SIZE];
    long long pending_start_price;
} Client;

typedef struct {
    char username[USERNAME_SIZE];
    char password[PASSWORD_SIZE];
    int is_logged_in;
    int client_fd;
} User;

typedef struct {
    int room_id;
    char room_name[ROOM_NAME_SIZE];
    char owner[USERNAME_SIZE];
    int member_count;
    int current_item_id;  /* 0: phong chua co vat pham dang dau gia */
    int is_active;
} AuctionRoom;

typedef enum {
    ITEM_PENDING,
    ITEM_AUCTIONING,
    ITEM_ENDED
} ItemStatus;

typedef struct {
    int item_id;
    int room_id;
    char name[ITEM_NAME_SIZE];
    long long start_price;
    long long buy_now_price;
    long long current_price;
    int highest_bidder;   /* Chi so user, -1: chua co nguoi dat gia */
    ItemStatus status;
    int is_active;
} AuctionItem;

/* Dinh nghia that cac bien nay nam trong server.c */
extern Client clients[MAX_CLIENTS];
extern User users[MAX_USERS];
extern AuctionRoom rooms[MAX_ROOMS];
extern AuctionItem items[MAX_ITEMS];
extern int user_count;
extern int next_room_id;
extern int next_item_id;

/* Ham gui du lieu duoc dinh nghia trong server.c */
int send_all(int socket_fd, const char *data, int length);
int send_message(int socket_fd, const char *message);

#endif
