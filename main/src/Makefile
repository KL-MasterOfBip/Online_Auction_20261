CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -g
TARGET = auction_server
SERVER_SRC = server.c client_handler.c user.c room.c logger.c

all: $(TARGET) client

$(TARGET): $(SERVER_SRC) common.h client_handler.h user.h room.h logger.h
	$(CC) $(CFLAGS) $(SERVER_SRC) -o $(TARGET)

client: client.c
	$(CC) $(CFLAGS) client.c -o client

clean:
	rm -f $(TARGET) client

.PHONY: all clean
