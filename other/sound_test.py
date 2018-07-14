from machine import Pin
import time
from micropython import const


NOTE_B0 = const(31)
NOTE_C1 = const(33)
NOTE_CS1 = const(35)
NOTE_D1 = const(37)
NOTE_DS1 = const(39)
NOTE_E1 = const(41)
NOTE_F1 = const(44)
NOTE_FS1 = const(46)
NOTE_G1 = const(49)
NOTE_GS1 = const(52)
NOTE_A1 = const(55)
NOTE_AS1 = const(58)
NOTE_B1 = const(62)
NOTE_C2 = const(65)
NOTE_CS2 = const(69)
NOTE_D2 = const(73)
NOTE_DS2 = const(78)
NOTE_E2 = const(82)
NOTE_F2 = const(87)
NOTE_FS2 = const(93)
NOTE_G2 = const(98)
NOTE_GS2 = const(104)
NOTE_A2 = const(110)
NOTE_AS2 = const(117)
NOTE_B2 = const(123)
NOTE_C3 = const(131)
NOTE_CS3 = const(139)
NOTE_D3 = const(147)
NOTE_DS3 = const(156)
NOTE_E3 = const(165)
NOTE_F3 = const(175)
NOTE_FS3 = const(185)
NOTE_G3 = const(196)
NOTE_GS3 = const(208)
NOTE_A3 = const(220)
NOTE_AS3 = const(233)
NOTE_B3 = const(247)
NOTE_C4 = const(262)
NOTE_CS4 = const(277)
NOTE_D4 = const(294)
NOTE_DS4 = const(311)
NOTE_E4 = const(330)
NOTE_F4 = const(349)
NOTE_FS4 = const(370)
NOTE_G4 = const(392)
NOTE_GS4 = const(415)
NOTE_A4 = const(440)
NOTE_AS4 = const(466)
NOTE_B4 = const(494)
NOTE_C5 = const(523)
NOTE_CS5 = const(554)
NOTE_D5 = const(587)
NOTE_DS5 = const(622)
NOTE_E5 = const(659)
NOTE_F5 = const(698)
NOTE_FS5 = const(740)
NOTE_G5 = const(784)
NOTE_GS5 = const(831)
NOTE_A5 = const(880)
NOTE_AS5 = const(932)
NOTE_B5 = const(988)
NOTE_C6 = const(1047)
NOTE_CS6 = const(1109)
NOTE_D6 = const(1175)
NOTE_DS6 = const(1245)
NOTE_E6 = const(1319)
NOTE_F6 = const(1397)
NOTE_FS6 = const(1480)
NOTE_G6 = const(1568)
NOTE_GS6 = const(1661)
NOTE_A6 = const(1760)
NOTE_AS6 = const(1865)
NOTE_B6 = const(1976)
NOTE_C7 = const(2093)
NOTE_CS7 = const(2217)
NOTE_D7 = const(2349)
NOTE_DS7 = const(2489)
NOTE_E7 = const(2637)
NOTE_F7 = const(2794)
NOTE_FS7 = const(2960)
NOTE_G7 = const(3136)
NOTE_GS7 = const(3322)
NOTE_A7 = const(3520)
NOTE_AS7 = const(3729)
NOTE_B7 = const(3951)
NOTE_C8 = const(4186)
NOTE_CS8 = const(4435)
NOTE_D8 = const(4699)
NOTE_DS8 = const(4978)


def tone(buzzer, freq, dur):
    # """ buzzer = pin object for the low trigger buzzer output
    #     freq = frequency in Hertz
    #     dur = duration in ms """
    delay = int(500000 / freq)
    cycles = int(freq * dur / 1000)
    for i in range(cycles):
        buzzer(0)
        time.sleep_us(delay)
        buzzer(1)
        time.sleep_us(delay)


def melody(buzzer, freq_list, len_list):
    # """ plays a list of notes (length given as 2 for half, 4 for quarter, ...) """

    for freq, length in zip(freq_list, len_list):
        dur = 1000 / length  # duration of the tone in ms
        if freq != 0:
            tone(buzzer, freq, dur)  # play the tone
        time.sleep_ms(int(dur))  # wait some time to distinguish the note
        #tone(buzzer, 0, dur)  # stop playing
        

def mario_melody():
    main_melody = [
      NOTE_E7, NOTE_E7, 0, NOTE_E7,
      0, NOTE_C7, NOTE_E7, 0,
      NOTE_G7, 0, 0,  0,
      NOTE_G6, 0, 0, 0,
     
      NOTE_C7, 0, 0, NOTE_G6,
      0, 0, NOTE_E6, 0,
      0, NOTE_A6, 0, NOTE_B6,
      0, NOTE_AS6, NOTE_A6, 0,
     
      NOTE_G6, NOTE_E7, NOTE_G7,
      NOTE_A7, 0, NOTE_F7, NOTE_G7,
      0, NOTE_E7, 0, NOTE_C7,
      NOTE_D7, NOTE_B6, 0, 0,
     
      NOTE_C7, 0, 0, NOTE_G6,
      0, 0, NOTE_E6, 0,
      0, NOTE_A6, 0, NOTE_B6,
      0, NOTE_AS6, NOTE_A6, 0,
     
      NOTE_G6, NOTE_E7, NOTE_G7,
      NOTE_A7, 0, NOTE_F7, NOTE_G7,
      0, NOTE_E7, 0, NOTE_C7,
      NOTE_D7, NOTE_B6, 0, 0
    ]

    main_tempo = [
      12, 12, 12, 12,
      12, 12, 12, 12,
      12, 12, 12, 12,
      12, 12, 12, 12,
     
      12, 12, 12, 12,
      12, 12, 12, 12,
      12, 12, 12, 12,
      12, 12, 12, 12,
     
      9, 9, 9,
      12, 12, 12, 12,
      12, 12, 12, 12,
      12, 12, 12, 12,
     
      12, 12, 12, 12,
      12, 12, 12, 12,
      12, 12, 12, 12,
      12, 12, 12, 12,
     
      9, 9, 9,
      12, 12, 12, 12,
      12, 12, 12, 12,
      12, 12, 12, 12,
    ]

    underworld_melody = [
      NOTE_C4, NOTE_C5, NOTE_A3, NOTE_A4,
      NOTE_AS3, NOTE_AS4, 0,
      0,
      NOTE_C4, NOTE_C5, NOTE_A3, NOTE_A4,
      NOTE_AS3, NOTE_AS4, 0,
      0,
      NOTE_F3, NOTE_F4, NOTE_D3, NOTE_D4,
      NOTE_DS3, NOTE_DS4, 0,
      0,
      NOTE_F3, NOTE_F4, NOTE_D3, NOTE_D4,
      NOTE_DS3, NOTE_DS4, 0,
      0, NOTE_DS4, NOTE_CS4, NOTE_D4,
      NOTE_CS4, NOTE_DS4,
      NOTE_DS4, NOTE_GS3,
      NOTE_G3, NOTE_CS4,
      NOTE_C4, NOTE_FS4, NOTE_F4, NOTE_E3, NOTE_AS4, NOTE_A4,
      NOTE_GS4, NOTE_DS4, NOTE_B3,
      NOTE_AS3, NOTE_A3, NOTE_GS3,
      0, 0, 0
    ]

    underworld_tempo = [
      12, 12, 12, 12,
      12, 12, 6,
      3,
      12, 12, 12, 12,
      12, 12, 6,
      3,
      12, 12, 12, 12,
      12, 12, 6,
      3,
      12, 12, 12, 12,
      12, 12, 6,
      6, 18, 18, 18,
      6, 6,
      6, 6,
      6, 6,
      18, 18, 18, 18, 18, 18,
      10, 10, 10,
      10, 10, 10,
      3, 3, 3
    ]

    buzzer = Pin(12, Pin.OUT, value=1)  # low trigger buzzer
    while True:
        melody(buzzer, main_melody, main_tempo)
        melody(buzzer, main_melody, main_tempo)
        melody(buzzer, underworld_melody, underworld_tempo)


def get_higher():
    buzzer = Pin(12, Pin.OUT, value=1)  # low trigger buzzer
    for freq in range(1, 20000, 1):
        tone(buzzer, freq, 100)
        print(freq)


get_higher()
