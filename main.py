import numpy as np
import cupy as cp
import pandas as pd
import time
import math
import sys
import cv2
import os
import pathlib

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame


# Sim settings
scrw = 1280  # screen width
scrh = 720  # screen height
scrsplit = 0.7  # screen split - board | stats, eff 896px
maxfps = int(60)  # max FPS limit
zoomsens = 1.008  # zoom sensitivity, multiplicative
sim_speed = 100  # sim updates per second - not sure if this would work with maxfps??
textcolor = "White"
textbg = "Black"
pause = True  # Start paused
buttonclr = "cadetblue"

# Initialize pygame & game setup:
pygame.init()
screen = pygame.display.set_mode((scrw, scrh))
pygame.display.set_caption("Abiogenesis simulator")
font = pygame.font.Font('freesansbold.ttf', 28)
font_big = pygame.font.Font('freesansbold.ttf', 50)
clock = pygame.time.Clock()

currfps = font.render('Current FPS: ',
                      True,
                      textcolor,
                      textbg
                      )
currfpsRect = currfps.get_rect()
currfpsRect.left = (scrw * scrsplit * 1.03)
currfpsRect.top = (scrh * 0.05)
fps = 0
fpstext = font.render(str(fps),
                      True,
                      textcolor,
                      textbg)
fpsRect = fpstext.get_rect()
fpsRect.left = currfpsRect.right * 1.01
fpsRect.top = currfpsRect.top
cst = font.render('Scale: ',
                  True,
                  textcolor,
                  textbg)
cstRect = cst.get_rect()
cstRect.left = (scrw * scrsplit * 1.03)
cstRect.top = currfpsRect.bottom * 1.1
csnt = font.render(str(cellsize),
                   True,
                   textcolor,
                   textbg)
csntRect = csnt.get_rect()
csntRect.left = cstRect.right * 1.01
csntRect.top = cstRect.top
butxt = font.render('Updates: ',
                    True,
                    textcolor,
                    textbg)
butxtRect = butxt.get_rect()
butxtRect.left = (scrw * scrsplit * 1.03)
butxtRect.top = cstRect.bottom * 1.1
bups = 0  # board updates so far
bupstext = font.render(str(bups),
                       True,
                       textcolor,
                       textbg)
bupsRect = bupstext.get_rect()
bupsRect.left = butxtRect.right * 1.01
bupsRect.top = butxtRect.top
lff = font_big.render('Load demo',
                      True,
                      textcolor,
                      buttonclr)
lffRect = lff.get_rect()
lffRect.top = bupsRect.bottom * 1.1
lffRect.left = int(scrw * scrsplit * 1.03)
clrdem = font_big.render('Clear demo',
                         True,
                         textcolor,
                         buttonclr)
clrdemRect = clrdem.get_rect()
clrdemRect.top = lffRect.bottom * 1.01
clrdemRect.left = lffRect.left
clrbrd = font_big.render('Clear board',
                         True,
                         textcolor,
                         buttonclr)
clrbrdRect = clrbrd.get_rect()
clrbrdRect.top = clrdemRect.bottom * 1.1
clrbrdRect.left = clrdemRect.left

# Auto-set parameters
dt = 0  # time elapsed (in ms)
bh = int(bh)
bw = int(bw)
ube_f = maxfps * update_board_every_s
board = np.zeros((bw, bh), dtype=np.uint8)
cam_pos = [bw / 2, bh / 2]
cps = base_cps * math.pow(cellsize, -0.6)
set_zoom_in = False
set_zoom_out = False
undohist = []
currundos = 0
i = 0
board_gpu = cp.asarray(board, dtype=cp.uint32)
record = []
isrecording = False
isplayingdemo = False
topause = False

cppsource = r'''
extern "C"
{
__global__ void render(const float* inps, const unsigned int* board, int* scrn)
    {
        unsigned int i = (blockIdx.x * blockDim.x) + threadIdx.x;
        unsigned int j = (blockIdx.y * blockDim.y) + threadIdx.y;
        unsigned int ylim = gridDim.y * blockDim.y;
        unsigned int indx = j + (i * ylim);
        unsigned int xlim = gridDim.x * blockDim.x;
        if (indx < xlim * ylim)
        {
            float bx = 0;
            float by = 0;
            float cs = 1;
            float cpx = 0;
            float cpy = 0;
            int bw = 100;
            int bh = 100;
            float fracx = 0;
            float fracy = 0;
            int b_x = 0;
            int b_y = 0;

            cpx = *(inps + 0);
            cpy = *(inps + 1);
            cs = *(inps + 2);
            bw = *(inps + 3);
            bh = *(inps + 4);

            bx = (i / cs) + cpx;
            by = (j / cs) + cpy;
            b_x = static_cast<int>(bx);
            b_y = static_cast<int>(by);
            fracx = bx - b_x;
            fracy = by - b_y;
            if(bx >= 0 && by >= 0 && b_x < bw && b_y < bh && fracx >= 0.1 && fracy >= 0.1)
            {
                unsigned int bval = *(board + b_y + (bh * b_x));
                if(bval == 0)
                {
                    *(scrn + (3 * indx)) = 20;
                    *(scrn + (3 * indx) + 1) = 20;
                    *(scrn + (3 * indx) + 2) = 20;
                } else if (bval == 1)
                {
                    *(scrn + (3 * indx)) = 20;
                    *(scrn + (3 * indx) + 1) = 55;
                    *(scrn + (3 * indx) + 2) = 20;
                } else if (bval == 2)
                {
                    *(scrn + (3 * indx)) = 30;
                    *(scrn + (3 * indx) + 1) = 255;
                    *(scrn + (3 * indx) + 2) = 30;
                } else
                {
                    *(scrn + (3 * indx)) = 0;
                    *(scrn + (3 * indx) + 1) = 255;
                    *(scrn + (3 * indx) + 2) = 0;
                }
            }
            else
            {
                *(scrn + (3 * indx)) = 0;
                *(scrn + (3 * indx) + 1) = 0;
                *(scrn + (3 * indx) + 2) = 0;
            }
        }
    }

__global__ void update(const unsigned int* inps, unsigned int* board)
    {
        unsigned int i = (blockIdx.x * blockDim.x) + threadIdx.x;
        unsigned int j = (blockIdx.y * blockDim.y) + threadIdx.y;
        unsigned int b_w = *(inps + 0);
        unsigned int b_h = *(inps + 1);
        unsigned int tid = j + (i * b_h);
        if(tid < b_w * b_h)
        {
            unsigned int leftind = 0;
            unsigned int rightind = 0;
            unsigned int topind = 0;
            unsigned int bottomind = 0;
            int cnt = 0;
            int cnt2 = 0;

            leftind = (((i - 1) + b_w) % b_w);
            rightind = (i + 1) % b_w;
            topind = (((j - 1) + b_h) % b_h);
            bottomind = (j + 1) % b_h;

            if(*(board + topind + (b_h * i)) == 1)
            {
                cnt++;
            }
            if(*(board + topind + (b_h * rightind)) == 1)
            {
                cnt++;
            }
            if(*(board + j + (b_h * rightind)) == 1)
            {
                cnt++;
            }
            if(*(board + bottomind + (b_h * rightind)) == 1)
            {
                cnt++;
            }
            if(*(board + bottomind + (b_h * i)) == 1)
            {
                cnt++;
            }
            if(*(board + bottomind + (b_h * leftind)) == 1)
            {
                cnt++;
            }
            if(*(board + j + (b_h * leftind)) == 1)
            {
                cnt++;
            }
            if(*(board + topind + (b_h * leftind)) == 1)
            {
                cnt++;
            }

            if(*(board + topind + (b_h * i)) == 2)
            {
                cnt2++;
            }
            if(*(board + topind + (b_h * rightind)) == 2)
            {
                cnt2++;
            }
            if(*(board + j + (b_h * rightind)) == 2)
            {
                cnt2++;
            }
            if(*(board + bottomind + (b_h * rightind)) == 2)
            {
                cnt2++;
            }
            if(*(board + bottomind + (b_h * i)) == 2)
            {
                cnt2++;
            }
            if(*(board + bottomind + (b_h * leftind)) == 2)
            {
                cnt2++;
            }
            if(*(board + j + (b_h * leftind)) == 2)
            {
                cnt2++;
            }
            if(*(board + topind + (b_h * leftind)) == 2)
            {
                cnt2++;
            }
            __syncthreads();
            if(cnt == 0)
            {
                if(cnt2 == 0)
                {
                    *(board + j + (b_h * i)) = 0;
                }
                else if(*(board + topind + (b_h * leftind)) == 2)
                {
                    *(board + j + (b_h * i)) = 1;
                }
            }
            if(cnt == 1 && cnt2 == 1 && *(board + j + (b_h * i)) == 1)
            {
                *(board + j + (b_h * i)) = 2;
            }
            if(cnt > 3)
            {
                *(board + j + (b_h * i)) = 0;
            }
            __syncthreads();
        }
    }
}
'''
gpgpumodule = cp.RawModule(code=cppsource)
rendergpu = gpgpumodule.get_function('render')
updateboard = gpgpumodule.get_function('update')


def renderer():
    screenarr = cp.zeros((int(scrw * scrsplit), scrh, 3), dtype=cp.uint32)

    args = cp.array([cam_pos[0],
                     cam_pos[1],
                     cellsize,
                     bw,
                     bh], dtype=cp.float32)
    rendergpu((int((scrw * scrsplit) / 32), int(scrh / 16)), (32, 16),
              (args,
               board_gpu,
               screenarr))

    _ = screenarr.get()
    return _


def board_update():
    global board
    args = cp.array([bw, bh], dtype=cp.uint32)
    updateboard((int(bw / 24), int(bh / 24)), (24, 24), (args, board_gpu))
    board = board_gpu.get()


def saverectofile():
    arrr = np.array(record, dtype=np.uint8)
    np.save('D:/PyProjects/CellularAutomata/saves/' + fname, arrr)


def loaddemo():
    t = np.load('D:/PyProjects/CellularAutomata/saves/' + fname)
    return t


def clrboard():
    global board, board_gpu
    board = np.zeros((bw, bh), dtype=np.uint8)
    board_gpu = cp.zeros((bw, bh), dtype=cp.uint32)


# Main game loop:
while True:
    for event in pygame.event.get():
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            bx = int((mx / cellsize) + cam_pos[0])
            by = int((my / cellsize) + cam_pos[1])
            if pausetxtRect.collidepoint(mx, my):
                pause = not pause
            if recordtxtRect.collidepoint(mx, my) and not isplayingdemo:
                if isrecording:
                    saverectofile()
                    record = []
                isrecording = not isrecording
                pause = True
            if lffRect.collidepoint(mx, my):
                _ = loaddemo()
                if _ is not None:
                    pause = False
                    topause = True
                    pausein = i + 5
                    isrecording = False
                    isplayingdemo = True
                    bups = 0
                    demolength = len(_)
            if clrdemRect.collidepoint(mx, my) and isplayingdemo:
                clrboard()
                isplayingdemo = False
            if clrbrdRect.collidepoint(mx, my) and not isplayingdemo and not isrecording:
                clrboard()
                pause = True
            if event.button == 1 and not isplayingdemo:
                if mx < int(scrw * scrsplit) and my < int(scrh):
                    if 0 <= bx < bw and 0 <= by < bh:
                        if currundos < max_undos:
                            undohist.append([bx, by, board[bx][by]])
                            currundos += 1
                        else:
                            undohist.append([bx, by, board[bx][by]])
                            undohist.pop(0)
                        board[bx][by] = (board[bx][by] + 1) % 3
                        board_gpu[bx][by] = (board_gpu[bx][by] + 1) % 3
            if event.button == 6:
                set_zoom_in = True
            if event.button == 7:
                set_zoom_out = True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_z and currundos > 0 and not isplayingdemo:
                bx, by, tmp = undohist.pop()
                board[bx][by] = tmp
                board_gpu[bx][by] = tmp
                currundos -= 1
        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 6:
                set_zoom_in = False
            if event.button == 7:
                set_zoom_out = False
        if event.type == pygame.QUIT:
            pygame.quit()
            print("User quit")
            sys.exit()

    if pygame.mouse.get_pressed()[2] and not isplayingdemo:
        mx, my = pygame.mouse.get_pos()
        bx = int((mx / cellsize) + cam_pos[0])
        by = int((my / cellsize) + cam_pos[1])
        if mx < int(scrw * scrsplit) and my < int(scrh):
            if bw > bx >= 0 and bh > by >= 0:
                if board[bx][by] != 0:
                    if currundos < max_undos:
                        undohist.append([bx, by, board[bx][by]])
                        currundos += 1
                    else:
                        undohist.append([bx, by, board[bx][by]])
                        undohist.pop(0)
                    board[bx][by] = 0
                    board_gpu[bx][by] = 0

    if pause:
        pausetxt = font_big.render('Paused', True, textcolor, "firebrick4")
    else:
        pausetxt = font_big.render('Pause', True, textcolor, "darkslategray")

    if isrecording:
        recordtxt = font.render('Recording...', True, "chartreuse1", buttonclr)
    else:
        recordtxt = font.render('Record', True, textcolor, buttonclr)

    if set_zoom_in:
        if cellsize > 1:
            cellsize /= zoomsens
    if set_zoom_out:
        cellsize *= zoomsens

    pausetxtRect = pausetxt.get_rect()
    pausetxtRect.left = (scrw * scrsplit * 1.1)
    pausetxtRect.bottom = scrh * 0.9

    recordtxtRect = recordtxt.get_rect()
    recordtxtRect.left = (scrw * scrsplit * 1.05)
    recordtxtRect.bottom = scrh * 0.7

    if (i % ube_f) == int(ube_f / 2) and not pause:
        if isplayingdemo is False:
            if isrecording:
                record.append(board)
            board_update()
            bups += 1
        else:
            board = _[bups].copy().astype(np.uint8)
            board_gpu = cp.array(_[bups], dtype=cp.uint32)
            if bups < demolength - 1:
                bups += 1

    scrn = np.zeros((scrw, scrh, 3), dtype=np.uint8)
    fps = clock.get_fps()
    fpstext = font.render(str(f'{fps:.2f}'), True, textcolor, textbg)
    csnt = font.render(str(f'{cellsize:.2f}'), True, textcolor, textbg)
    bupstext = font.render(str(bups), True, textcolor, textbg)

    scrn[0:int(scrw * scrsplit)][:] = renderer()

    pygame.surfarray.blit_array(screen, scrn)
    pygame.draw.line(screen,
                     textcolor,
                     (int(scrw * scrsplit), 0),
                     (int(scrw * scrsplit), scrh),
                     3
                     )
    pygame.draw.rect(screen,
                     textbg,
                     pygame.Rect(scrw * scrsplit,
                                 0,
                                 scrw * (1 - scrsplit),
                                 scrh
                                 )
                     )
    screen.blit(currfps, currfpsRect)
    screen.blit(fpstext, fpsRect)
    screen.blit(csnt, csntRect)
    screen.blit(cst, cstRect)
    screen.blit(bupstext, bupsRect)
    screen.blit(butxt, butxtRect)
    screen.blit(pausetxt, pausetxtRect)
    screen.blit(recordtxt, recordtxtRect)
    screen.blit(lff, lffRect)
    screen.blit(clrdem, clrdemRect)
    screen.blit(clrbrd, clrbrdRect)

    # Input handling:
    keys = pygame.key.get_pressed()
    if keys[pygame.K_w]:
        cam_pos[1] -= cps * (dt / 1000)
    if keys[pygame.K_s]:
        cam_pos[1] += cps * (dt / 1000)
    if keys[pygame.K_a]:
        cam_pos[0] -= cps * (dt / 1000)
    if keys[pygame.K_d]:
        cam_pos[0] += cps * (dt / 1000)

    cps = base_cps * math.pow(cellsize, -0.6)
    # Render
    pygame.display.flip()

    if topause and i == pausein:
        pause = True
        topause = False

    dt = clock.tick(maxfps)
    i += 1