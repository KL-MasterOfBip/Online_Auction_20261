CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -g
TARGET = server
SOURCE = src/server.c src/client_handler.c src/user.c src/room.c src/item.c src/logger.c
HEADERS = $(wildcard src/*.h)

all: $(TARGET) client

$(TARGET): $(SOURCE) $(HEADERS)
	$(CC) $(CFLAGS) $(SOURCE) -o $(TARGET)

client: src/client.c
	$(CC) $(CFLAGS) src/client.c -o client

clean:
	rm -f $(TARGET) client

.PHONY: all clean
