/*
 * ktap – minimaler Touch-Leser für Kindle (Linux evdev).
 *
 *   ktap info                      Touch-Gerät und Wertebereiche anzeigen
 *   ktap once [timeout_s]          auf einen Tap warten, "x y rawx rawy" ausgeben
 *   ktap serve                     Befehle auf stdin:
 *                                    "w <timeout_s>"  -> nächsten Tap als "x y" oder "timeout"
 *                                    "q"              -> beenden
 *
 * Optionen (vor dem Befehl):
 *   -d /dev/input/eventN   Gerät (sonst automatisch: erstes mit ABS_MT_POSITION_X bzw. ABS_X)
 *   -W breite -H höhe      Bildschirmgröße für die Skalierung (Standard 1072x1448)
 *   -s                     x/y tauschen
 *   -x / -y                x bzw. y spiegeln (nach dem Tauschen)
 *   -g                     Gerät NICHT exklusiv greifen (Standard: EVIOCGRAB, damit die
 *                          Kindle-Oberfläche die Taps nicht auch bekommt)
 *
 * Nur Taps (Finger hoch) werden gemeldet; Position = letzte Position vor dem Loslassen.
 * Taps, die vor einem "w"-Befehl passiert sind, werden verworfen.
 */

#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

#ifndef ABS_MT_POSITION_X
#define ABS_MT_POSITION_X 0x35
#define ABS_MT_POSITION_Y 0x36
#define ABS_MT_TRACKING_ID 0x39
#endif
#ifndef SYN_MT_REPORT
#define SYN_MT_REPORT 2
#endif

#define BITS_PER_LONG (sizeof(long) * 8)
#define NBITS(x) ((((x) - 1) / BITS_PER_LONG) + 1)
#define TEST_BIT(bit, arr) ((arr[(bit) / BITS_PER_LONG] >> ((bit) % BITS_PER_LONG)) & 1)

/* Kindle-Kernel (3.0, 32 Bit) liefert 16-Byte-Events; musl mit 64-Bit-time_t muss dazu passen */
typedef char input_event_is_16_bytes[sizeof(struct input_event) == 16 ? 1 : -1];

static int scr_w = 1072, scr_h = 1448, swap_xy = 0, inv_x = 0, inv_y = 0, grab = 1;
static int code_x = ABS_MT_POSITION_X, code_y = ABS_MT_POSITION_Y;
static struct input_absinfo ax, ay;

static int has_abs(int fd, int code) {
    unsigned long bits[NBITS(ABS_MAX + 1)];
    memset(bits, 0, sizeof bits);
    if (ioctl(fd, EVIOCGBIT(EV_ABS, sizeof bits), bits) < 0) return 0;
    return TEST_BIT(code, bits);
}

static int open_touch(const char *path) {
    char buf[64];
    int i, fd;
    for (i = path ? -1 : 0; i < 16; i++) {
        const char *p = path;
        if (!p) { snprintf(buf, sizeof buf, "/dev/input/event%d", i); p = buf; }
        fd = open(p, O_RDONLY | O_NONBLOCK);
        if (fd < 0) { if (path) return -1; continue; }
        if (has_abs(fd, ABS_MT_POSITION_X)) { code_x = ABS_MT_POSITION_X; code_y = ABS_MT_POSITION_Y; }
        else if (has_abs(fd, ABS_X)) { code_x = ABS_X; code_y = ABS_Y; }
        else { close(fd); if (path) return -1; continue; }
        if (ioctl(fd, EVIOCGABS(code_x), &ax) < 0 || ioctl(fd, EVIOCGABS(code_y), &ay) < 0) {
            close(fd); if (path) return -1; continue;
        }
        if (!path) fprintf(stderr, "ktap: using %s\n", p);
        return fd;
    }
    return -1;
}

static int scale(int v, const struct input_absinfo *a, int size) {
    int range = a->maximum - a->minimum;
    if (range <= 0) return v;
    long s = (long)(v - a->minimum) * (size - 1) / range;
    if (s < 0) s = 0;
    if (s > size - 1) s = size - 1;
    return (int)s;
}

static void to_screen(int rx, int ry, int *sx, int *sy) {
    int x, y;
    if (swap_xy) { x = scale(ry, &ay, scr_w); y = scale(rx, &ax, scr_h); }
    else         { x = scale(rx, &ax, scr_w); y = scale(ry, &ay, scr_h); }
    if (inv_x) x = scr_w - 1 - x;
    if (inv_y) y = scr_h - 1 - y;
    *sx = x; *sy = y;
}

/* Touch-Zustand */
static int down = 0, frame_pos = 0, frame_mt = 0, last_rx = -1, last_ry = -1;

/* Verarbeitet ein Event; gibt 1 zurück, wenn ein Tap (Finger hoch) fertig ist. */
static int feed(const struct input_event *ev) {
    if (ev->type == EV_ABS) {
        if (ev->code == code_x) { last_rx = ev->value; frame_pos = 1; down = 1; }
        else if (ev->code == code_y) { last_ry = ev->value; frame_pos = 1; down = 1; }
        else if (ev->code == ABS_MT_TRACKING_ID) {
            if (ev->value >= 0) down = 1;
            else if (down) { down = 0; return last_rx >= 0; }
        }
    } else if (ev->type == EV_KEY && ev->code == BTN_TOUCH) {
        if (ev->value) down = 1;
        else if (down) { down = 0; return last_rx >= 0; }
    } else if (ev->type == EV_SYN) {
        if (ev->code == SYN_MT_REPORT) frame_mt = 1;
        else if (ev->code == SYN_REPORT) {
            /* Protokoll A: leerer Frame bedeutet Finger hoch */
            int up = down && frame_mt && !frame_pos;
            frame_pos = frame_mt = 0;
            if (up) { down = 0; return last_rx >= 0; }
        }
    }
    return 0;
}

static void drain(int fd) {
    struct input_event ev;
    while (read(fd, &ev, sizeof ev) == sizeof ev) feed(&ev);
    down = 0; frame_pos = frame_mt = 0;
}

/* Wartet auf einen Tap. 1 = Tap, 0 = Timeout, -1 = Fehler/stdin zu (nur serve). */
static int wait_tap(int fd, int timeout_s, int watch_stdin, int *rx, int *ry) {
    struct timeval deadline, now, tv;
    gettimeofday(&deadline, NULL);
    deadline.tv_sec += timeout_s;
    for (;;) {
        fd_set fds;
        FD_ZERO(&fds);
        FD_SET(fd, &fds);
        if (watch_stdin) FD_SET(0, &fds);
        gettimeofday(&now, NULL);
        long ms = (deadline.tv_sec - now.tv_sec) * 1000L + (deadline.tv_usec - now.tv_usec) / 1000L;
        if (timeout_s > 0 && ms <= 0) return 0;
        tv.tv_sec = ms / 1000; tv.tv_usec = (ms % 1000) * 1000;
        int r = select(fd + 1, &fds, NULL, NULL, timeout_s > 0 ? &tv : NULL);
        if (r < 0) { if (errno == EINTR) continue; return -1; }
        if (r == 0) return 0;
        if (watch_stdin && FD_ISSET(0, &fds)) {
            char c;
            if (read(0, &c, 1) <= 0) return -1; /* Steuer-Pipe geschlossen */
        }
        if (FD_ISSET(fd, &fds)) {
            struct input_event ev;
            ssize_t n;
            while ((n = read(fd, &ev, sizeof ev)) == sizeof ev) {
                if (feed(&ev)) { *rx = last_rx; *ry = last_ry; return 1; }
            }
            if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) return -1;
        }
    }
}

static int read_line(char *buf, int size) {
    int n = 0;
    char c;
    while (n < size - 1) {
        ssize_t r = read(0, &c, 1);
        if (r <= 0) return -1;
        if (c == '\n') break;
        buf[n++] = c;
    }
    buf[n] = 0;
    return n;
}

static void usage(void) {
    fprintf(stderr, "usage: ktap [-d dev] [-W w] [-H h] [-s] [-x] [-y] [-g] info|once [timeout]|serve\n");
    exit(2);
}

int main(int argc, char **argv) {
    const char *dev = NULL;
    int i = 1;
    for (; i < argc && argv[i][0] == '-'; i++) {
        const char *a = argv[i];
        if (!strcmp(a, "-d") && i + 1 < argc) dev = argv[++i];
        else if (!strcmp(a, "-W") && i + 1 < argc) scr_w = atoi(argv[++i]);
        else if (!strcmp(a, "-H") && i + 1 < argc) scr_h = atoi(argv[++i]);
        else if (!strcmp(a, "-s")) swap_xy = 1;
        else if (!strcmp(a, "-x")) inv_x = 1;
        else if (!strcmp(a, "-y")) inv_y = 1;
        else if (!strcmp(a, "-g")) grab = 0;
        else usage();
    }
    if (i >= argc) usage();
    const char *cmd = argv[i];

#ifdef KTAP_TEST
    /* Testmodus: Events aus Datei abspielen, Wertebereich 0..4095 */
    if (!strcmp(cmd, "replay") && i + 1 < argc) {
        int f = open(argv[i + 1], O_RDONLY), sx, sy;
        struct input_event ev;
        ax.maximum = ay.maximum = 4095;
        while (read(f, &ev, sizeof ev) == sizeof ev)
            if (feed(&ev)) { to_screen(last_rx, last_ry, &sx, &sy); printf("%d %d\n", sx, sy); }
        return 0;
    }
#endif
    int fd = open_touch(dev);
    if (fd < 0) { fprintf(stderr, "ktap: no touch device found\n"); return 1; }

    if (!strcmp(cmd, "info")) {
        char name[128] = "?";
        ioctl(fd, EVIOCGNAME(sizeof name), name);
        printf("name=%s\ncodes=%s\nx=%d..%d\ny=%d..%d\nscreen=%dx%d\n", name,
               code_x == ABS_MT_POSITION_X ? "mt" : "abs", ax.minimum, ax.maximum, ay.minimum, ay.maximum,
               scr_w, scr_h);
        return 0;
    }

    if (grab && ioctl(fd, EVIOCGRAB, 1) < 0) fprintf(stderr, "ktap: EVIOCGRAB failed: %s\n", strerror(errno));
    setvbuf(stdout, NULL, _IOLBF, 0);

    if (!strcmp(cmd, "once")) {
        int to = i + 1 < argc ? atoi(argv[i + 1]) : 0, rx, ry, sx, sy;
        drain(fd);
        int r = wait_tap(fd, to, 0, &rx, &ry);
        if (r != 1) { printf("timeout\n"); return 3; }
        to_screen(rx, ry, &sx, &sy);
        printf("%d %d %d %d\n", sx, sy, rx, ry);
        return 0;
    }

    if (!strcmp(cmd, "serve")) {
        char line[64];
        while (read_line(line, sizeof line) >= 0) {
            if (line[0] == 'q') break;
            if (line[0] != 'w') continue;
            int to = atoi(line + 1), rx, ry, sx, sy;
            drain(fd);
            int r = wait_tap(fd, to, 0, &rx, &ry);
            if (r == 1) { to_screen(rx, ry, &sx, &sy); printf("%d %d\n", sx, sy); }
            else if (r == 0) printf("timeout\n");
            else { printf("error\n"); break; }
        }
        return 0;
    }
    usage();
    return 2;
}
