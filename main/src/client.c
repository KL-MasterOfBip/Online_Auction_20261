#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <signal.h>
#include <termios.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <arpa/inet.h>

#define SERVER_IP "127.0.0.1"
#define SERVER_PORT 8080
#define BUFFER_SIZE 4096

static struct termios saved_terminal;
static int password_hidden = 0;
static volatile sig_atomic_t interrupted = 0;

/* Luon tra lai echo khi ket thuc, gap loi hoac nhan Ctrl+C. */
void restore_terminal(void) {
    if (password_hidden) {
        tcsetattr(STDIN_FILENO, TCSANOW, &saved_terminal);
        password_hidden = 0;
        putchar('\n');
        fflush(stdout);
    }
}

void handle_signal(int signum) {
    (void)signum;
    interrupted = 1;
}

int hide_password(void) {
    if (!isatty(STDIN_FILENO)) {
        return 0;
    }
    if (tcgetattr(STDIN_FILENO, &saved_terminal) < 0) {
        return -1;
    }
    struct termios terminal = saved_terminal;
    terminal.c_lflag &= (tcflag_t)~(ECHO | ECHONL);
    if (tcsetattr(STDIN_FILENO, TCSANOW, &terminal) < 0) {
        return -1;
    }
    password_hidden = 1;
    return 0;
}

int send_all(int socket_fd, const char *data, size_t length) {
    size_t total = 0;
    while (total < length && !interrupted) {
        ssize_t sent = send(socket_fd, data + total, length - total, 0);
        if (sent < 0 && errno == EINTR) {
            continue;
        }
        if (sent <= 0) {
            return -1;
        }
        total += (size_t)sent;
    }
    return total == length ? 0 : -1;
}

/* Phan hoi TCP theo dong; chi prompt password moi tat echo terminal. */
int display_response(char *line) {
    int password_prompt = strcmp(line, "New password:") == 0 ||
                          strcmp(line, "Password:") == 0;
    int username_prompt = strcmp(line, "New username:") == 0 ||
                          strcmp(line, "Username:") == 0;
    int room_prompt = strcmp(line, "Room name:") == 0 ||
                      strcmp(line, "Room ID:") == 0;
    if (password_prompt && hide_password() < 0) {
        perror("Cannot hide password");
        return -1;
    }
    if (password_prompt || username_prompt || room_prompt) {
        printf("%s ", line);
    }
    else {
        puts(line);
    }
    fflush(stdout);
    return 0;
}

int main(int argc, char *argv[]) {
    // Lay dia chi server, mac dinh la 127.0.0.1:8080.
    const char *host = SERVER_IP;
    long port = SERVER_PORT;
    if (argc > 1) {
        host = argv[1];
    }
    if (argc > 3) {
        fprintf(stderr, "Usage: %s [IPv4 address] [port]\n", argv[0]);
        return 1;
    }
    if (argc > 2) {
        char *end;
        errno = 0;
        port = strtol(argv[2], &end, 10);
        if (errno || *end || end == argv[2] || port < 1 || port > 65535) {
            fprintf(stderr, "Invalid port\n");
            return 1;
        }
    }

    // Nhan tin hieu de thoat vong lap va khoi phuc terminal.
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = handle_signal;
    sigemptyset(&action.sa_mask);
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGHUP, &action, NULL);
    sigaction(SIGQUIT, &action, NULL);
    signal(SIGPIPE, SIG_IGN);

    // Tao socket TCP.
    int client = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (client < 0) {
        perror("socket");
        return 1;
    }
    if (client >= FD_SETSIZE) {
        fprintf(stderr, "Socket descriptor exceeds select limit\n");
        close(client);
        return 1;
    }
    // Khai bao dia chi server.
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((unsigned short)port);
    if (inet_pton(AF_INET, host, &addr.sin_addr) != 1) {
        fprintf(stderr, "Invalid IPv4 address\n");
        close(client);
        return 1;
    }
    // Ket noi den server.
    if (connect(client, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("connect");
        close(client);
        return 1;
    }

    // Chuan bi buffer va theo doi ban phim cung socket bang select().
    fd_set fdread;
    char response[BUFFER_SIZE];
    size_t response_length = 0;
    int stdin_open = 1;
    int result = 0;
    while (!interrupted) {
        // select() thay doi fd_set, can khoi tao lai sau moi vong lap.
        FD_ZERO(&fdread);
        FD_SET(client, &fdread);
        if (stdin_open) {
            FD_SET(STDIN_FILENO, &fdread);
        }
        // Cho du lieu tu server hoac ban phim.
        int ready = select(client + 1, &fdread, NULL, NULL, NULL);
        if (ready < 0) {
            if (errno == EINTR) {
                continue;
            }
            perror("select");
            result = 1;
            break;
        }
        // Nhan tu server truoc de hien prompt va an password kip thoi.
        if (FD_ISSET(client, &fdread)) {
            char incoming[BUFFER_SIZE];
            ssize_t received = recv(client, incoming, sizeof(incoming), 0);
            if (received < 0 && errno == EINTR) {
                continue;
            }
            if (received <= 0) {
                if (received < 0) {
                    perror("recv");
                    result = 1;
                }
                break;
            }
            // TCP co the tach/gop dong, giu phan chua nhan du trong buffer.
            for (ssize_t i = 0; i < received; i++) {
                if (incoming[i] == '\n') {
                    response[response_length] = '\0';
                    if (display_response(response) < 0) {
                        result = 1;
                        break;
                    }
                    response_length = 0;
                }
                else if (response_length < sizeof(response) - 1) {
                    response[response_length++] = incoming[i];
                }
                else {
                    fprintf(stderr, "Server response too long\n");
                    result = 1;
                    break;
                }
            }
        }
        if (result != 0) {
            break;
        }

        // Doc ban phim va gui du lieu den server.
        if (!interrupted && stdin_open && FD_ISSET(STDIN_FILENO, &fdread)) {
            char input[BUFFER_SIZE];
            // Dung read() de khong co buffer stdin doc truoc du lieu cua select().
            ssize_t length = read(STDIN_FILENO, input, sizeof(input));
            if (length < 0 && errno == EINTR) {
                continue;
            }
            restore_terminal();
            if (length <= 0) {
                memset(input, 0, sizeof(input));
                if (length < 0) {
                    perror("read");
                    result = 1;
                    break;
                }
                // Ctrl+D: ngung gui, tiep tuc nhan phan hoi con lai.
                shutdown(client, SHUT_WR);
                stdin_open = 0;
            }
            else {
                int sent = send_all(client, input, (size_t)length);
                memset(input, 0, sizeof(input));
                if (sent < 0) {
                    if (!interrupted) {
                        perror("send");
                    }
                    result = 1;
                    break;
                }
            }
        }
    }

    // Ket thuc: khoi phuc hien thi ban phim roi dong socket.
    restore_terminal();
    close(client);
    return result;
}
