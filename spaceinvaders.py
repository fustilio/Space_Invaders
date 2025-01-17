#!/usr/bin/env python

# Space Invaders
# Created by Lee Robinson

from pygame import *
import sys
from os.path import abspath, dirname
from random import choice
import numpy as np
from enum import Enum

from model.circuit_grid_model import CircuitGridModel
from controls.circuit_grid import CircuitGrid, CircuitGridNode
from copy import deepcopy

from utils.navigation import MOVE_UP, MOVE_DOWN, MOVE_LEFT, MOVE_RIGHT
from utils.parameters import WIDTH_UNIT, WINDOW_HEIGHT, WINDOW_WIDTH, \
    LEFT, RIGHT, NOTHING, NO, YES, MEASURE_LEFT, MEASURE_RIGHT, WINDOW_SIZE
from qiskit import BasicAer, execute, ClassicalRegister

BASE_PATH = abspath(dirname(__file__))
FONT_PATH = BASE_PATH + '/fonts/'
IMAGE_PATH = BASE_PATH + '/images/'
SOUND_PATH = BASE_PATH + '/sounds/'

# Colors (R, G, B)
WHITE = (255, 255, 255)
GREEN = (78, 255, 87)
YELLOW = (241, 255, 0)
BLUE = (80, 255, 239)
PURPLE = (203, 0, 255)
RED = (237, 28, 36)

#SCREEN_HEIGHT = 640
SCREEN_HEIGHT = 300
SCREEN = display.set_mode((800, 640))
#screen = display.set_mode(WINDOW_SIZE)
FONT = FONT_PATH + 'space_invaders.ttf'
IMG_NAMES = ['ship', 'mystery',
             'enemy1_1', 'enemy1_2',
             'enemy2_1', 'enemy2_2',
             'enemy3_1', 'enemy3_2',
             'explosionblue', 'explosiongreen', 'explosionpurple',
             'laser', 'enemylaser']
IMAGES = {name: image.load(IMAGE_PATH + '{}.png'.format(name)).convert_alpha()
          for name in IMG_NAMES}
POSITIONS = [20, 120, 220, 320, 420, 520, 620, 720]
# OFFSETS = [-100, 0, -200, 100, -300, 200, -400, 300]
OFFSETS = [-400, -300, -200, -100, 0, 100, 200, 300]
DISTRIBUTIONS = [25.0, 25.0, 15.0, 15.0, 7.0, 7.0, 3.0, 3.0]
LABEL_TEXT = ["|000>", "|001>", "|010>", "|011>", "|100>", "|101>", "|110>", "|111>"]

NUMBER_OF_SHIPS = 8

BLOCKERS_POSITION = 450
ENEMY_DEFAULT_POSITION = 65  # Initial value for a new game
ENEMY_MOVE_DOWN = 35
ENEMY_HEALTH = 96

BULLET_MAX_DAMAGE = 96

class ShipState(Enum):
    SUPERPOSITION = 0
    MEASURED = 1


class Ship(sprite.Sprite):
    def __init__(self, id):
        sprite.Sprite.__init__(self)
        self.id = id
        self.probability = DISTRIBUTIONS[id] / 100.0
        self.image = IMAGES['ship'].copy()
        self.image.fill((255, 255, 255, self.probability * 500), None, BLEND_RGBA_MULT)
        self.speed = 5
        self.rect = self.image.get_rect(topleft=(POSITIONS[self.id], 540))
        self.classical = False

    def update(self, *args):
        self.update_opacity(self.probability)
        game.screen.blit(self.image, self.rect)

    def fire(self, measuring, measured_ship):
        if measuring:
            if self is measured_ship:
                bullet = Bullet(self.rect.x + 23,
                                self.rect.y + 5, -1,
                                15, 'laser', 'center', 1.0)
                game.bullets.add(bullet)
                game.allSprites.add(game.bullets)
                game.sounds['shoot'].play()

        else:
            bullet = Bullet(self.rect.x + 23,
                            self.rect.y + 5, -1,
                            15, 'laser', 'center', self.probability)
            game.bullets.add(bullet)
            game.allSprites.add(game.bullets)
            game.sounds['shoot'].play()

    def update_opacity(self, prob):
        self.image = IMAGES['ship'].copy()
        opacity = 0
        if self.classical:
            opacity = 1
        else:
            if prob > 0.75:
                opacity = 1
            elif prob > 0.5:
                opacity = 0.8
            elif prob > 0.25:
                opacity = 0.6
            elif prob > 0.1:
                opacity = 0.35
        self.image.fill((255, 255, 255, opacity * 255), None, BLEND_RGBA_MULT)

class ShipGroup(sprite.Group):
    def __init__(self, number_of_ships, position):
        sprite.Group.__init__(self)
        self.ships = [None] * number_of_ships
        self.number_of_ships = number_of_ships
        self.position = position
        self.measured_ship = None
        self.measuring = False
        self.timer = 0.0
        self.state = ShipState.SUPERPOSITION

    def update(self, keys, *args):
        passed = time.get_ticks() - self.timer
        if self.measuring and passed > 600:
            self.measuring = False

        for ship in self:
            if self.state == ShipState.SUPERPOSITION:
                ship.classical = False
                ship.rect.x = (OFFSETS[ship.id] + POSITIONS[self.position]) % 800
            elif self.state == ShipState.MEASURED:
                if ship == self.measured_ship:
                    ship.classical = True
                    ship.rect.x = (OFFSETS[ship.id] + POSITIONS[self.position]) % 800
                else:
                    ship.rect.x = 999999999
            ship.update_opacity(ship.probability)
            ship.update()

    def add_internal(self, *sprites):
        super(ShipGroup, self).add_internal(*sprites)
        for s in sprites:
            self.ships[s.id] = s

    def remove_internal(self, *sprites):
        super(ShipGroup, self).remove_internal(*sprites)
        for s in sprites:
            self.kill(s)

    def fire(self):
        for ship in self:
            ship.fire(self.state == ShipState.MEASURED, self.measured_ship)

    def kill(self, ship):
        self.ships[ship.id] = None

    def explode_ships(self, explosionsGroup, measured_ship_id):
        for ship in self.ships:
            if ship is not None:
                if ship.id == measured_ship_id:
                    ship.update_opacity(1.0)
                    ship.update()
                    self.measured_ship = ship
                else:
                    ship.kill()

                # ShipExplosion(ship, sprite.Group())

    def update_probabilities(self, probabilities):
        for ship in self:
            p_amp = probabilities[ship.id]
            ship.probability = p_amp.real*p_amp.real + p_amp.imag*p_amp.imag
            ship.update_opacity(ship.probability)

    def measure(self, measured_ship_id):
        for ship in self.ships:
            if ship is not None:
                if ship.id == measured_ship_id:
                    self.measured_ship = ship
        self.measuring = True
        self.timer = time.get_ticks()
        self.state = ShipState.MEASURED
        self.update([])

    def draw(self, screen):
        for ship in self.ships:
            if ship is not None and ship is Ship:
                text = Text(FONT, 50, '000', WHITE, 50, 50)
                text.draw(screen)


class Bullet(sprite.Sprite):
    def __init__(self, xpos, ypos, direction, speed, filename, side, multiplier=1.0):
        sprite.Sprite.__init__(self)
        self.image = IMAGES[filename]
        self.rect = self.image.get_rect(topleft=(xpos, ypos))
        self.speed = speed
        self.direction = direction
        self.side = side
        self.filename = filename
        self.multiplier = multiplier
        self.damage = BULLET_MAX_DAMAGE * multiplier + 1  # accounting for floating point issue

    def update(self, keys, *args):
        self.image = IMAGES[self.filename].copy()
        alpha = 0
        if self.multiplier > 0.01: # if alpha is above 0 basically
            alpha = max(self.multiplier * 255, 128)
        self.image.fill((255, 255, 255, alpha), None, BLEND_RGBA_MULT)
        game.screen.blit(self.image, self.rect)
        self.rect.y += self.speed * self.direction
        if self.rect.y < 15 or self.rect.y > 650:
            self.kill()


class Enemy(sprite.Sprite):
    def __init__(self, row, column):
        sprite.Sprite.__init__(self)
        self.row = row
        self.column = column
        self.images = []
        self.load_images()
        self.index = 0
        self.image = self.images[self.index]
        self.rect = self.image.get_rect()
        self.health = ENEMY_HEALTH

    def toggle_image(self):
        self.index = (self.index + 1) % len(self.images)
        self.image = self.images[self.index]

    def update(self, *args):
        self.image = self.images[self.index].copy()
        alpha = max(255 * self.health / ENEMY_HEALTH, 50)
        self.image.fill((255, 255, 255, alpha), None, BLEND_RGBA_MULT)
        game.screen.blit(self.image, self.rect)

    def load_images(self):
        images = {0: ['1_2', '1_1'],
                  1: ['2_2', '2_1'],
                  2: ['2_2', '2_1'],
                  3: ['3_1', '3_2'],
                  4: ['3_1', '3_2'],
                  }
        img1, img2 = (IMAGES['enemy{}'.format(img_num)] for img_num in
                      images[self.row])
        self.images.append(transform.scale(img1, (40, 35)))
        self.images.append(transform.scale(img2, (40, 35)))


class EnemiesGroup(sprite.Group):
    def __init__(self, columns, rows):
        sprite.Group.__init__(self)
        self.enemies = [[None] * columns for _ in range(rows)]
        self.columns = columns
        self.rows = rows
        self.leftAddMove = 0
        self.rightAddMove = 0
        self.moveTime = 600
        self.direction = 1
        self.rightMoves = 30
        self.leftMoves = 30
        self.moveNumber = 15
        self.timer = time.get_ticks()
        self.bottom = game.enemyPosition + ((rows - 1) * 45) + 35
        self._aliveColumns = list(range(columns))
        self._leftAliveColumn = 0
        self._rightAliveColumn = columns - 1

    def update(self, current_time):
        if current_time - self.timer > self.moveTime:
            if self.direction == 1:
                max_move = self.rightMoves + self.rightAddMove
            else:
                max_move = self.leftMoves + self.leftAddMove

            if self.moveNumber >= max_move:
                self.leftMoves = 30 + self.rightAddMove
                self.rightMoves = 30 + self.leftAddMove
                self.direction *= -1
                self.moveNumber = 0
                self.bottom = 0
                for enemy in self:
                    enemy.rect.y += ENEMY_MOVE_DOWN
                    enemy.toggle_image()
                    if self.bottom < enemy.rect.y + 35:
                        self.bottom = enemy.rect.y + 35
            else:
                velocity = 10 if self.direction == 1 else -10
                for enemy in self:
                    enemy.rect.x += velocity
                    enemy.toggle_image()
                self.moveNumber += 1

            self.timer = current_time + self.moveTime

    def add_internal(self, *sprites):
        super(EnemiesGroup, self).add_internal(*sprites)
        for s in sprites:
            self.enemies[s.row][s.column] = s

    def remove_internal(self, *sprites):
        super(EnemiesGroup, self).remove_internal(*sprites)
        for s in sprites:
            self.kill(s)
        self.update_speed()

    def is_column_dead(self, column):
        return not any(self.enemies[row][column]
                       for row in range(self.rows))

    def random_bottom(self):
        col = choice(self._aliveColumns)
        col_enemies = (self.enemies[row - 1][col]
                       for row in range(self.rows, 0, -1))
        return next((en for en in col_enemies if en is not None), None)

    def update_speed(self):
        if len(self) == 1:
            self.moveTime = 200
        elif len(self) <= 10:
            self.moveTime = 400

    def kill(self, enemy):
        self.enemies[enemy.row][enemy.column] = None
        is_column_dead = self.is_column_dead(enemy.column)
        if is_column_dead:
            self._aliveColumns.remove(enemy.column)

        if enemy.column == self._rightAliveColumn:
            while self._rightAliveColumn > 0 and is_column_dead:
                self._rightAliveColumn -= 1
                self.rightAddMove += 5
                is_column_dead = self.is_column_dead(self._rightAliveColumn)

        elif enemy.column == self._leftAliveColumn:
            while self._leftAliveColumn < self.columns and is_column_dead:
                self._leftAliveColumn += 1
                self.leftAddMove += 5
                is_column_dead = self.is_column_dead(self._leftAliveColumn)


class Blocker(sprite.Sprite):
    def __init__(self, size, color, row, column):
        sprite.Sprite.__init__(self)
        self.height = size
        self.width = size
        self.color = color
        self.image = Surface((self.width, self.height))
        self.image.fill(self.color)
        self.rect = self.image.get_rect()
        self.row = row
        self.column = column

    def update(self, keys, *args):
        game.screen.blit(self.image, self.rect)


class Mystery(sprite.Sprite):
    def __init__(self):
        sprite.Sprite.__init__(self)
        self.image = IMAGES['mystery']
        self.image = transform.scale(self.image, (75, 35))
        self.rect = self.image.get_rect(topleft=(-80, 45))
        self.row = 5
        self.moveTime = 25000
        self.direction = 1
        self.timer = time.get_ticks()
        self.mysteryEntered = mixer.Sound(SOUND_PATH + 'mysteryentered.wav')
        self.mysteryEntered.set_volume(0.3)
        self.playSound = True

    def update(self, keys, currentTime, *args):
        resetTimer = False
        passed = currentTime - self.timer
        if passed > self.moveTime:
            if (self.rect.x < 0 or self.rect.x > 800) and self.playSound:
                self.mysteryEntered.play()
                self.playSound = False
            if self.rect.x < 840 and self.direction == 1:
                self.mysteryEntered.fadeout(4000)
                self.rect.x += 2
                game.screen.blit(self.image, self.rect)
            if self.rect.x > -100 and self.direction == -1:
                self.mysteryEntered.fadeout(4000)
                self.rect.x -= 2
                game.screen.blit(self.image, self.rect)

        if self.rect.x > 830:
            self.playSound = True
            self.direction = -1
            resetTimer = True
        if self.rect.x < -90:
            self.playSound = True
            self.direction = 1
            resetTimer = True
        if passed > self.moveTime and resetTimer:
            self.timer = currentTime


class EnemyExplosion(sprite.Sprite):
    def __init__(self, enemy, *groups):
        super(EnemyExplosion, self).__init__(*groups)
        self.image = transform.scale(self.get_image(enemy.row), (40, 35))
        self.image2 = transform.scale(self.get_image(enemy.row), (50, 45))
        self.rect = self.image.get_rect(topleft=(enemy.rect.x, enemy.rect.y))
        self.timer = time.get_ticks()

    @staticmethod
    def get_image(row):
        img_colors = ['purple', 'blue', 'blue', 'green', 'green']
        return IMAGES['explosion{}'.format(img_colors[row])]

    def update(self, current_time, *args):
        passed = current_time - self.timer
        if passed <= 100:
            game.screen.blit(self.image, self.rect)
        elif passed <= 200:
            game.screen.blit(self.image2, (self.rect.x - 6, self.rect.y - 6))
        elif 400 < passed:
            self.kill()


class MysteryExplosion(sprite.Sprite):
    def __init__(self, mystery, score, *groups):
        super(MysteryExplosion, self).__init__(*groups)
        self.text = Text(FONT, 20, str(score), WHITE,
                         mystery.rect.x + 20, mystery.rect.y + 6)
        self.timer = time.get_ticks()

    def update(self, current_time, *args):
        passed = current_time - self.timer
        if passed <= 200 or 400 < passed <= 600:
            self.text.draw(game.screen)
        elif 600 < passed:
            self.kill()


class ShipExplosion(sprite.Sprite):
    def __init__(self, ship, *groups):
        super(ShipExplosion, self).__init__(*groups)
        self.image = IMAGES['ship']
        self.rect = self.image.get_rect(topleft=(ship.rect.x, ship.rect.y))
        self.timer = time.get_ticks()

    def update(self, current_time, *args):
        passed = current_time - self.timer
        if 300 < passed <= 600:
            game.screen.blit(self.image, self.rect)
        elif 900 < passed:
            self.kill()


class Life(sprite.Sprite):
    def __init__(self, xpos, ypos):
        sprite.Sprite.__init__(self)
        self.image = IMAGES['ship']
        self.image = transform.scale(self.image, (23, 23))
        self.rect = self.image.get_rect(topleft=(xpos, ypos))

    def update(self, *args):
        game.screen.blit(self.image, self.rect)


class Text(object):
    def __init__(self, textFont, size, message, color, xpos, ypos):
        self.font = font.Font(textFont, size)
        self.surface = self.font.render(message, True, color)
        self.rect = self.surface.get_rect(topleft=(xpos, ypos))

    def draw(self, surface):
        surface.blit(self.surface, self.rect)


class Labels(object):
    def __init__(self):
        self.labels = []

    def initialize(self, position):
        self.labels = []
        for i in range(8):
            self.labels.append(Text(FONT, 20, LABEL_TEXT[i], WHITE, POSITIONS[position] + OFFSETS[i], 600))

    def update(self, screen, position):
        for i in range(len(self.labels)):
            self.labels[i].rect = self.labels[i].surface.get_rect(topleft=((POSITIONS[position] + OFFSETS[i]) % 800, 600))
        for label in self.labels:
            label.draw(screen)
"""
class PauseBar(sprite.Sprite):
    def __init__(self, mystery, score, *groups):
        self.readytext = Text(FONT, 20, "QUANTUM READY", WHITE,
                         400, 0)
        self.text = Text(FONT, 20, "QUANTUM NOT READY", RED,
                         400, 0)
        self.timer = time.get_ticks()
        self.ready = False

    def update(self, current_time, *args):
        passed = current_time - self.timer
        if passed <= 600:
            self.text.draw(game.screen)
        elif 600 > passed:
            self.readytext.draw(game.screen)
            self.ready = True
            self.timer = currentTime
    
    def reset():
        self.ready = False
"""


class SpaceInvaders(object):
    def __init__(self):
        # It seems, in Linux buffersize=512 is not enough, use 4096 to prevent:
        #   ALSA lib pcm.c:7963:(snd_pcm_recover) underrun occurred
        mixer.pre_init(44100, -16, 1, 4096)
        init()
        self.clock = time.Clock()
        self.caption = display.set_caption('Space Invaders')
        self.screen = SCREEN
        self.background = image.load(IMAGE_PATH + 'qiskit.png').convert()
        self.startGame = False
        self.mainScreen = True
        self.gameOver = False
        # Counter for enemy starting position (increased each new round)
        self.enemyPosition = ENEMY_DEFAULT_POSITION
        self.titleText = Text(FONT, 50, 'Space Invaders', WHITE, 164, 155)
        self.titleText2 = Text(FONT, 25, 'Press any key to continue', WHITE,
                               201, 225)
        self.pauseText = Text(FONT, 42, 'Quantum Circuit Composer', WHITE, 50, 155)
        self.pauseText2 = Text(FONT, 25, 'Press ENTER key to continue', WHITE,
                               164, 225)
        self.gameOverText = Text(FONT, 50, 'Game Over', WHITE, 250, 270)
        self.nextRoundText = Text(FONT, 50, 'Next Round', WHITE, 240, 270)
        self.enemy1Text = Text(FONT, 25, '   =   10 pts', GREEN, 368, 270)
        self.enemy2Text = Text(FONT, 25, '   =  20 pts', BLUE, 368, 320)
        self.enemy3Text = Text(FONT, 25, '   =  30 pts', PURPLE, 368, 370)
        self.enemy4Text = Text(FONT, 25, '   =  ?????', RED, 368, 420)
        self.scoreText = Text(FONT, 20, 'Score', WHITE, 5, 5)
        self.livesText = Text(FONT, 20, 'Lives ', WHITE, 640, 5)

        self.life1 = Life(715, 3)
        self.life2 = Life(742, 3)
        self.life3 = Life(769, 3)
        self.livesGroup = sprite.Group(self.life1, self.life2, self.life3)

        self.shipPosition = 4

        self.circuit_grid_model = CircuitGridModel(3, 10)
        self.circuit_grid = CircuitGrid(0, SCREEN_HEIGHT , self.circuit_grid_model)
        self.paused = False
        #self.pause_bar = 0
        #self.pause_ready = False
        #self.pause_increment_time = 50

        self.labels = Labels()
        #self.pause_bar = PauseBar()

    def reset(self, score):
        self.player = ShipGroup(NUMBER_OF_SHIPS, self.shipPosition)
        self.make_ships()
        self.labels.initialize(self.player.position)
        self.playerGroup = sprite.Group(self.player)
        self.explosionsGroup = sprite.Group()
        self.bullets = sprite.Group()
        self.mysteryShip = Mystery()
        self.mysteryGroup = sprite.Group(self.mysteryShip)
        self.enemyBullets = sprite.Group()
        self.make_enemies()
        self.allSprites = sprite.Group(self.player, self.enemies,
                                       self.livesGroup, self.mysteryShip)
        self.keys = key.get_pressed()

        self.timer = time.get_ticks()
        self.noteTimer = time.get_ticks()
        self.shipTimer = time.get_ticks()
        self.score = score
        self.create_audio()
        self.makeNewShip = False
        self.shipAlive = True

    def make_blockers(self, number):
        blockerGroup = sprite.Group()
        for row in range(4):
            for column in range(9):
                blocker = Blocker(10, GREEN, row, column)
                blocker.rect.x = 50 + (200 * number) + (column * blocker.width)
                blocker.rect.y = BLOCKERS_POSITION + (row * blocker.height)
                blockerGroup.add(blocker)
        return blockerGroup

    def create_audio(self):
        mixer.init(48000, -16, 1, 1024)
        mixer.music.load('sounds/SG.mp3')
        mixer.music.play()
        mixer.music.set_volume(0.35)
        self.sounds = {}
        for sound_name in ['shoot', 'shoot2', 'invaderkilled', 'mysterykilled',
                           'shipexplosion']:
            self.sounds[sound_name] = mixer.Sound(
                SOUND_PATH + '{}.wav'.format(sound_name))
            self.sounds[sound_name].set_volume(0.2)

        self.musicNotes = [mixer.Sound(SOUND_PATH + '{}.wav'.format(i)) for i
                           in range(4)]
        for sound in self.musicNotes:
            sound.set_volume(0.5)

        self.noteIndex = 0

    def play_main_music(self, currentTime):
        if currentTime - self.noteTimer > self.enemies.moveTime:
            self.note = self.musicNotes[self.noteIndex]
            if self.noteIndex < 3:
                self.noteIndex += 1
            else:
                self.noteIndex = 0

            self.note.play()
            self.noteTimer += self.enemies.moveTime

    @staticmethod
    def should_exit(evt):
        # type: (pygame.event.EventType) -> bool
        return evt.type == QUIT or (evt.type == KEYUP and evt.key == K_ESCAPE)

    def get_probability_amplitudes(self, circuit, qubit_num, shot_num):
        backend_sv_sim = BasicAer.get_backend('statevector_simulator')
        job_sim = execute(circuit, backend_sv_sim, shots=shot_num)
        result_sim = job_sim.result()
        quantum_state = result_sim.get_statevector(circuit, decimals=3)
        return quantum_state
    
    def get_measurement(self, circuit, qubit_num, shot_num):
        backend_sv_sim = BasicAer.get_backend('qasm_simulator')
        cr = ClassicalRegister(qubit_num)
        measure_circuit = deepcopy(circuit)  # make a copy of circuit
        measure_circuit.add_register(cr)    # add classical registers for measurement readout
        measure_circuit.measure(measure_circuit.qregs[0], measure_circuit.cregs[0])
        job_sim = execute(measure_circuit, backend_sv_sim, shots=shot_num)
        result_sim = job_sim.result()
        counts = result_sim.get_counts(circuit)
        return int(list(counts.keys())[0], 2)

    def check_input(self):
        self.keys = key.get_pressed()
        for e in event.get():
            if self.should_exit(e):
                sys.exit()
            """      
            if e.type == KEYDOWN:
                if e.key == K_SPACE:
                    if len(self.bullets) == 0 and self.shipAlive:
                        if self.score < 1000:
                            self.player.fire()
                            # bullet = Bullet(self.player.rect.x + 23,
                            #                 self.player.rect.y + 5, -1,
                            #                 15, 'laser', 'center')
                            # self.bullets.add(bullet)
                            # self.allSprites.add(self.bullets)
                            # self.sounds['shoot'].play()
                        # else:
                        #     leftbullet = Bullet(self.player.rect.x + 8,
                        #                         self.player.rect.y + 5, -1,
                        #                         15, 'laser', 'left')
                        #     rightbullet = Bullet(self.player.rect.x + 38,
                        #                          self.player.rect.y + 5, -1,
                        #                          15, 'laser', 'right')
                        #     self.bullets.add(leftbullet)
                        #     self.bullets.add(rightbullet)
                        #     self.allSprites.add(self.bullets)
                        #     self.sounds['shoot2'].play()

            """
            if e.type == KEYDOWN:
                if e.key == K_ESCAPE:
                    self.running = False
                elif e.key == K_RETURN:
                    self.paused = not(self.paused)
                elif not self.paused:
                    if e.key == K_SPACE:
                        if len(self.bullets) == 0 and self.shipAlive:
                            self.player.fire()
                    elif e.key == K_o:
                        self.player.state = ShipState.SUPERPOSITION
                        if self.player.position >= 0:
                            self.player.position = (self.player.position - 1) % 8
                            self.player.update(self.keys)
                    elif e.key == K_p:
                        self.player.state = ShipState.SUPERPOSITION
                        if self.player.position <= 7:
                            self.player.position = (self.player.position + 1) % 8
                            self.player.update(self.keys)
                else:
                    if e.key == K_a:
                        self.circuit_grid.move_to_adjacent_node(MOVE_LEFT)
                    elif e.key == K_d:
                        self.circuit_grid.move_to_adjacent_node(MOVE_RIGHT)
                    elif e.key == K_w:
                        self.circuit_grid.move_to_adjacent_node(MOVE_UP)
                    elif e.key == K_s:
                        self.circuit_grid.move_to_adjacent_node(MOVE_DOWN)
                    elif e.key == K_x:
                        self.circuit_grid.handle_input_x()
                    elif e.key == K_y:
                        self.circuit_grid.handle_input_y()
                    elif e.key == K_z:
                        self.circuit_grid.handle_input_z()
                    elif e.key == K_h:
                        self.circuit_grid.handle_input_h()
                    elif e.key == K_BACKSPACE:
                        self.circuit_grid.handle_input_delete()
                    elif e.key == K_c:
                        # Add or remove a control
                        self.circuit_grid.handle_input_ctrl()
                    elif e.key == K_UP:
                        # Move a control qubit up
                        self.circuit_grid.handle_input_move_ctrl(MOVE_UP)
                    elif e.key == K_DOWN:
                        # Move a control qubit down
                        self.circuit_grid.handle_input_move_ctrl(MOVE_DOWN)
                    elif e.key == K_LEFT:
                        # Rotate a gate
                        self.circuit_grid.handle_input_rotate(-np.pi / 8)
                    elif e.key == K_RIGHT:
                        # Rotate a gate
                        self.circuit_grid.handle_input_rotate(np.pi / 8)
                    circuit = self.circuit_grid.circuit_grid_model.compute_circuit()
                    state = self.get_probability_amplitudes(circuit, 3, 100)
                    self.player.update_probabilities(state)
                    self.circuit_grid.draw(self.screen)
                    self.player.update(self.keys)
                    display.flip()

    def make_enemies(self):
        enemies = EnemiesGroup(10, 5)
        for row in range(5):
            for column in range(10):
                enemy = Enemy(row, column)
                enemy.rect.x = 157 + (column * 50)
                enemy.rect.y = self.enemyPosition + (row * 45)
                enemies.add(enemy)

        self.enemies = enemies

    def make_ships(self):
        ships = ShipGroup(NUMBER_OF_SHIPS, self.shipPosition)
        for i in range(NUMBER_OF_SHIPS):
            ship = Ship(i)
            ships.add(ship)
        ships.update([])
        self.player = ships
        circuit = self.circuit_grid.circuit_grid_model.compute_circuit()
        state = self.get_probability_amplitudes(circuit, 3, 100)
        self.player.update_probabilities(state)

    def make_enemies_shoot(self):
        if (time.get_ticks() - self.timer) > 700 and self.enemies:
            enemy = self.enemies.random_bottom()
            self.enemyBullets.add(
                Bullet(enemy.rect.x + 14, enemy.rect.y + 20, 1, 5,
                       'enemylaser', 'center'))
            self.allSprites.add(self.enemyBullets)
            self.timer = time.get_ticks()

    def calculate_score(self, row):
        scores = {0: 30,
                  1: 20,
                  2: 20,
                  3: 10,
                  4: 10,
                  5: choice([50, 100, 150, 300])
                  }

        score = scores[row]
        self.score += score
        return score

    def create_main_menu(self):
        self.enemy1 = IMAGES['enemy3_1']
        self.enemy1 = transform.scale(self.enemy1, (40, 40))
        self.enemy2 = IMAGES['enemy2_2']
        self.enemy2 = transform.scale(self.enemy2, (40, 40))
        self.enemy3 = IMAGES['enemy1_2']
        self.enemy3 = transform.scale(self.enemy3, (40, 40))
        self.enemy4 = IMAGES['mystery']
        self.enemy4 = transform.scale(self.enemy4, (80, 40))
        self.screen.blit(self.enemy1, (318, 270))
        self.screen.blit(self.enemy2, (318, 320))
        self.screen.blit(self.enemy3, (318, 370))
        self.screen.blit(self.enemy4, (299, 420))

    def check_collisions(self):
        sprite.groupcollide(self.bullets, self.enemyBullets, True, True)

        col = sprite.groupcollide(self.enemies, self.bullets, False, True)
        for enemy in col.keys():
            self.sounds['invaderkilled'].play()
            enemy.health -= col[enemy][0].damage
            if enemy.health <= 0:
                enemy.kill()
                self.calculate_score(enemy.row)
                EnemyExplosion(enemy, self.explosionsGroup)
                self.gameTimer = time.get_ticks()

        for mystery in sprite.groupcollide(self.mysteryGroup, self.bullets,
                                           True, True).keys():
            mystery.mysteryEntered.stop()
            self.sounds['mysterykilled'].play()
            score = self.calculate_score(mystery.row)
            MysteryExplosion(mystery, score, self.explosionsGroup)
            newShip = Mystery()
            self.allSprites.add(newShip)
            self.mysteryGroup.add(newShip)

        collision_handled = False

        circuit = self.circuit_grid.circuit_grid_model.compute_circuit()
        state = self.get_measurement(circuit, 3, 1)

        hits = sprite.groupcollide(self.playerGroup, self.enemyBullets,
                                          False, True)
        self.player.measuring = False

        if self.player.state == ShipState.SUPERPOSITION:
            for ship in hits:
                if ship.probability > 0.0:
                    self.player.measure(state)
                if state == ship.id:  # quantum case
                    if not collision_handled:
                        if self.life3.alive():
                            self.life3.kill()
                        elif self.life2.alive():
                            self.life2.kill()
                        elif self.life1.alive():
                            self.life1.kill()
                        else:
                            self.gameOver = True
                            self.startGame = False
                        self.sounds['shipexplosion'].play()
                        self.player.explode_ships(self.explosionsGroup, ship.id)
                        self.makeNewShip = True
                        self.shipPosition = self.player.position
                        self.shipTimer = time.get_ticks()
                        self.shipAlive = False

                        collision_handled = True
        elif self.player.state == ShipState.MEASURED:
            for ship in hits:
                print("collision detected, state is MEASURED")
                if not collision_handled:
                    if self.life3.alive():
                        self.life3.kill()
                    elif self.life2.alive():
                        self.life2.kill()
                    elif self.life1.alive():
                        self.life1.kill()
                    else:
                        self.gameOver = True
                        self.startGame = False
                    self.sounds['shipexplosion'].play()
                    self.player.explode_ships(self.explosionsGroup, -1)
                    self.makeNewShip = True
                    self.shipPosition = self.player.position
                    self.shipTimer = time.get_ticks()
                    self.shipAlive = False

                    collision_handled = True

        # for ship in hits:
        #     if not self.player.measuring and ship.probability > 0.0:
        #         self.player.measure(state)
        #         self.player.measuring = True


        if self.enemies.bottom >= 540:
            sprite.groupcollide(self.enemies, self.playerGroup, True, True)
            if not self.player.alive() or self.enemies.bottom >= 600:
                self.gameOver = True
                self.startGame = False

        sprite.groupcollide(self.bullets, self.allBlockers, True, True)
        sprite.groupcollide(self.enemyBullets, self.allBlockers, True, True)
        if self.enemies.bottom >= BLOCKERS_POSITION:
            sprite.groupcollide(self.enemies, self.allBlockers, False, True)

    def create_new_ship(self, createShip, currentTime):

        if createShip and (currentTime - self.shipTimer > 900):
            self.player = ShipGroup(NUMBER_OF_SHIPS, self.shipPosition)
            self.make_ships()
            self.labels.initialize(self.player.position)
            self.allSprites.add(self.player)
            self.playerGroup.add(self.player)
            self.makeNewShip = False
            self.shipAlive = True
        elif createShip and (currentTime - self.shipTimer > 300):
            if self.player.measured_ship:
                self.player.measured_ship.kill()

    def create_game_over(self, currentTime):
        self.screen.blit(self.background, (0, 0))
        passed = currentTime - self.timer
        if passed < 750:
            self.gameOverText.draw(self.screen)
        elif 750 < passed < 1500:
            self.screen.blit(self.background, (0, 0))
        elif 1500 < passed < 2250:
            self.gameOverText.draw(self.screen)
        elif 2250 < passed < 2750:
            self.screen.blit(self.background, (0, 0))
        elif passed > 3000:
            self.mainScreen = True

        for e in event.get():
            if self.should_exit(e):
                sys.exit()

    def main(self):
        while True:
            if self.mainScreen:
                self.screen.blit(self.background, (0, 0))
                self.titleText.draw(self.screen)
                self.titleText2.draw(self.screen)
                self.enemy1Text.draw(self.screen)
                self.enemy2Text.draw(self.screen)
                self.enemy3Text.draw(self.screen)
                self.enemy4Text.draw(self.screen)
                self.create_main_menu()
                for e in event.get():
                    if self.should_exit(e):
                        sys.exit()
                    if e.type == KEYUP:
                        # Only create blockers on a new game, not a new round
                        self.allBlockers = sprite.Group(self.make_blockers(0),
                                                        self.make_blockers(1),
                                                        self.make_blockers(2),
                                                        self.make_blockers(3))
                        self.livesGroup.add(self.life1, self.life2, self.life3)
                        self.reset(0)
                        self.startGame = True
                        self.mainScreen = False

            elif self.startGame:
                if not self.enemies and not self.explosionsGroup and not self.paused:
                    currentTime = time.get_ticks()
                    if currentTime - self.gameTimer < 3000:
                        self.screen.blit(self.background, (0, 0))
                        self.scoreText2 = Text(FONT, 20, str(self.score),
                                               GREEN, 85, 5)
                        self.scoreText.draw(self.screen)
                        self.scoreText2.draw(self.screen)
                        self.nextRoundText.draw(self.screen)
                        self.livesText.draw(self.screen)
                        #self.circuit_grid.draw(self.screen)
                        # self.player.draw(self.screen)
                        self.livesGroup.update()
                        self.check_input()
                        self.labels.update(self.screen, self.player.position)
                    if currentTime - self.gameTimer > 3000:
                        # Move enemies closer to bottom
                        self.enemyPosition += ENEMY_MOVE_DOWN
                        self.reset(self.score)
                        self.gameTimer += 3000
                else:

                    self.screen.blit(self.background, (0, 0))
                    self.allBlockers.update(self.screen)
                    self.scoreText2 = Text(FONT, 20, str(self.score), GREEN,
                                           85, 5)
                    self.scoreText.draw(self.screen)
                    self.scoreText2.draw(self.screen)
                    self.livesText.draw(self.screen)
                    #self.circuit_grid.draw(self.screen)
                    self.labels.update(self.screen, self.player.position)
                    # self.player.draw(self.screen)
                    self.check_input()
                    if not self.paused:
                        currentTime = time.get_ticks()
                        self.play_main_music(currentTime)
                        self.enemies.update(currentTime)
                        self.make_enemies_shoot()
                        self.allSprites.update(self.keys, currentTime)
                        self.explosionsGroup.update(currentTime)
                        self.check_collisions()
                        self.create_new_ship(self.makeNewShip, currentTime)
                    else:
                        self.pauseText.draw(self.screen)
                        self.pauseText2.draw(self.screen)
                        self.circuit_grid.draw(self.screen)
                        self.player.update(self.keys)
                    # self.ships.update(self.keys)
                    

            elif self.gameOver:
                currentTime = time.get_ticks()
                # Reset enemy starting position
                self.enemyPosition = ENEMY_DEFAULT_POSITION
                self.create_game_over(currentTime)

            display.update()
            self.clock.tick(60)


if __name__ == '__main__':
    game = SpaceInvaders()
    game.main()
