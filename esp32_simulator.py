#!/usr/bin/env python3

import paho.mqtt.client as mqtt
import json
import time
import random
from datetime import datetime

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
CELL_ID = 7
DEV_ID = "c07-nicolas_gabriela"

CAMPUS = "riodosul"
CURSO = "si"
TURMA = "BSN22025T26F8"

TOPIC_BASE = f"iot/{CAMPUS}/{CURSO}/{TURMA}/cell/{CELL_ID}/device/{DEV_ID}/"
TOPIC_STATE = TOPIC_BASE + "state"
TOPIC_TELEMETRY = TOPIC_BASE + "telemetry"
TOPIC_EVENT = TOPIC_BASE + "event"
TOPIC_CMD = TOPIC_BASE + "cmd"
TOPIC_CONFIG = TOPIC_BASE + "config"

STATUS_NORMAL = "normal"
STATUS_ATENCAO = "atencao"
STATUS_CRITICO = "critico"

class ESP32Simulator:
    def __init__(self):
        self.client = mqtt.Client(client_id=DEV_ID)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.will_set(TOPIC_STATE, "offline", qos=1, retain=True)
        
        self.vib_warn = 300
        self.vib_alarm = 600
        self.histerese = 20
        
        self.current_status = STATUS_NORMAL
        self.previous_status = STATUS_NORMAL
        
        self.vib_index = 150
        self.vib_trend = 1
        
    def on_connect(self, client, userdata, flags, rc):
        print(f"[MQTT] Conectado com código: {rc}")
        client.subscribe(TOPIC_CMD, qos=1)
        print(f"[MQTT] Inscrito em: {TOPIC_CMD}")
        
        client.publish(TOPIC_STATE, "online", qos=1, retain=True)
        print(f"[STATE] Publicado: online")
        
        self.publish_config()
        
    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode('utf-8')
            print(f"[CMD] Recebido: {payload}")
            
            cmd = json.loads(payload)
            action = cmd.get("action")
            
            if action == "get_status":
                print("[CMD] Executando get_status...")
                self.publish_telemetry(force=True)
                
            elif action == "set_thresholds":
                data = cmd.get("data", {})
                new_warn = data.get("vib_warn", self.vib_warn)
                new_alarm = data.get("vib_alarm", self.vib_alarm)
                
                if 0 <= new_warn <= 1000 and 0 <= new_alarm <= 1000 and new_warn < new_alarm:
                    self.vib_warn = new_warn
                    self.vib_alarm = new_alarm
                    print(f"[CMD] Limiares atualizados: warn={self.vib_warn}, alarm={self.vib_alarm}")
                    self.publish_config()
                    self.publish_telemetry(force=True)
                else:
                    print("[CMD] Limiares inválidos")
                    
        except Exception as e:
            print(f"[CMD] Erro ao processar comando: {e}")
    
    def classify_status(self, vib_index):
        if self.current_status == STATUS_NORMAL:
            if vib_index < self.vib_warn + self.histerese:
                return STATUS_NORMAL
        
        if self.current_status == STATUS_ATENCAO:
            if (self.vib_warn - self.histerese) <= vib_index <= (self.vib_alarm + self.histerese):
                return STATUS_ATENCAO
        
        if self.current_status == STATUS_CRITICO:
            if vib_index > self.vib_alarm - self.histerese:
                return STATUS_CRITICO
        
        if vib_index < self.vib_warn:
            return STATUS_NORMAL
        elif vib_index <= self.vib_alarm:
            return STATUS_ATENCAO
        else:
            return STATUS_CRITICO
    
    def publish_config(self):
        config = {
            "cellId": CELL_ID,
            "devId": DEV_ID,
            "thresholds": {
                "vib_warn": self.vib_warn,
                "vib_alarm": self.vib_alarm
            },
            "misc": {
                "telemetry_interval_ms": 3000
            }
        }
        
        payload = json.dumps(config)
        self.client.publish(TOPIC_CONFIG, payload, qos=1, retain=True)
        print(f"[CONFIG] Publicado: {payload}")
    
    def publish_telemetry(self, force=False):
        telemetry = {
            "ts": int(time.time()),
            "cellId": CELL_ID,
            "devId": DEV_ID,
            "metrics": {
                "vib_index": self.vib_index
            },
            "status": self.current_status,
            "thresholds": {
                "vib_warn": self.vib_warn,
                "vib_alarm": self.vib_alarm
            }
        }
        
        payload = json.dumps(telemetry)
        self.client.publish(TOPIC_TELEMETRY, payload, qos=0)
        print(f"[TELEMETRY] Publicado: vib_index={self.vib_index}, status={self.current_status}")
    
    def publish_event(self, event_type, from_status, to_status):
        event = {
            "ts": int(time.time()),
            "type": event_type,
            "from": from_status,
            "to": to_status,
            "vib_index": self.vib_index
        }
        
        payload = json.dumps(event)
        self.client.publish(TOPIC_EVENT, payload, qos=0)
        print(f"[EVENT] Publicado: {event_type} - {from_status} -> {to_status}")
    
    def simulate_sensor(self):
        self.vib_index += self.vib_trend * random.randint(5, 25)
        
        if self.vib_index >= 950:
            self.vib_trend = -1
        elif self.vib_index <= 50:
            self.vib_trend = 1
        
        if random.random() < 0.1:
            self.vib_index += random.randint(-50, 50)
        
        self.vib_index = max(0, min(1000, self.vib_index))
    
    def run(self):
        print(f"[INIT] Conectando ao broker MQTT em {MQTT_BROKER}:{MQTT_PORT}")
        self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
        self.client.loop_start()
        
        time.sleep(2)
        
        print("[INIT] Simulador iniciado. Pressione Ctrl+C para parar.")
        
        try:
            while True:
                self.simulate_sensor()
                
                new_status = self.classify_status(self.vib_index)
                
                if new_status != self.current_status:
                    self.previous_status = self.current_status
                    self.current_status = new_status
                    
                    event_type = "alarme_vibracao" if new_status == STATUS_CRITICO else "mudanca_status"
                    self.publish_event(event_type, self.previous_status, self.current_status)
                    self.publish_telemetry(force=True)
                else:
                    self.publish_telemetry()
                
                time.sleep(3)
                
        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Encerrando simulador...")
            self.client.publish(TOPIC_STATE, "offline", qos=1, retain=True)
            self.client.loop_stop()
            self.client.disconnect()

if __name__ == "__main__":
    simulator = ESP32Simulator()
    simulator.run()
