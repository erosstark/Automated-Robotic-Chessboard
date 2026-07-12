#include "FastAccelStepper.h"
#include <ServoTimer2.h>

// 1. Definições de pinos
#define PIN_SLEEP 7
#define PIN_DIR_X  8
#define PIN_STEP_X 9
#define PIN_DIR_Y  11
#define PIN_STEP_Y 10
#define PIN_SERVO 12
#define PIN_MICROSTEPx 2
#define PIN_MICROSTEPy 3
// Configurações de movimento
const float VELOCIDADE_MAX_BASE = 5000.0;
const float ACELERACAO_MAX_BASE = 10000.0;
const int STEPS_PER_SQUARE = 275; // ainda preciso definir  
const int OFFSET = 18;             

FastAccelStepperEngine engine = FastAccelStepperEngine();
FastAccelStepper *motorX = NULL;
FastAccelStepper *motorY = NULL;
ServoTimer2 gripper;

char modoAtual = 'P'; 
bool debugAtivo = true; // Flag para ativar/desativar prints de debug

// Funções Auxiliares
void moverParaPassos(long alvoX, long alvoY);
long coordParaPassos(int c);
void processarTrajetoria();
void processarCalibracao();

// move servo
void setServo(int pos) {
  int pulseWidth = map(pos, 0, 180, 750, 2250);
  gripper.write(pulseWidth);
  
  if (debugAtivo) {
    Serial.print("[DEBUG] Servo: ");
    Serial.print(pos);
    Serial.print(" (PWM: ");
    Serial.print(pulseWidth);
    Serial.println(")");
  }
}

void setup() {
  Serial.begin(115200);
  
  // Configura pino de SLEEP do A4988 (HIGH = Ativo, LOW = Dormindo)
  pinMode(PIN_SLEEP, OUTPUT);
  digitalWrite(PIN_SLEEP, HIGH);
  pinMode(PIN_MICROSTEPy, OUTPUT);
  digitalWrite(PIN_MICROSTEPy, HIGH);
  pinMode(PIN_MICROSTEPx, OUTPUT);
  digitalWrite(PIN_MICROSTEPx, HIGH);
  // 1. Inicializa motores
  engine.init();
  motorX = engine.stepperConnectToPin(PIN_STEP_X);
  motorY = engine.stepperConnectToPin(PIN_STEP_Y);
  if (motorX && motorY) {
    motorX->setDirectionPin(PIN_DIR_X);
    motorY->setDirectionPin(PIN_DIR_Y);
    
    // Inicializa velocidade e aceleração padrão para calibração
    motorX->setSpeedInHz(VELOCIDADE_MAX_BASE);
    motorX->setAcceleration(ACELERACAO_MAX_BASE);
    motorY->setSpeedInHz(VELOCIDADE_MAX_BASE);
    motorY->setAcceleration(ACELERACAO_MAX_BASE);
  }

  // 2. Inicializa Servo na posição padrão (0 - abaixado)
  gripper.attach(PIN_SERVO);
  setServo(180);

  Serial.println("SISTEMA PRONTO");
}

void loop() {
  if (Serial.available() > 0) {
    char cmd = Serial.read();

    // Comando para alternar Debug
    if (cmd == 'D') {
      debugAtivo = !debugAtivo;
      Serial.print("DEBUG ");
      Serial.println(debugAtivo ? "ATIVADO" : "DESATIVADO");
    }
    // Troca de modo
    else if (cmd == 'P') {
      modoAtual = 'P';
      setServo(180); // Retorna servo para 0 ao sair da calibração
      Serial.println("MODO JOGO ATIVO");
    } 
    else if (cmd == 'C') {
      modoAtual = 'C';
      setServo(40); // Abre/Sobe servo para calibração visual
      Serial.println("MODO CALIBRACAO ATIVO");
    } 
    
    // Execução dependente do modo
    else if (modoAtual == 'P') {
      if (cmd == 'T') {
        processarTrajetoria();
      } else if (cmd == 'H') {
        if (debugAtivo) Serial.println("[DEBUG] Comando Home (Jogo)");
        digitalWrite(PIN_SLEEP, LOW);
        delay(2); // Tempo para o driver acordar
        moverParaPassos(0, 0); 
        digitalWrite(PIN_SLEEP, HIGH);
        Serial.println("HOME OK");
      }
    } 
    else if (modoAtual == 'C') {
      if (cmd == 'K') {
        processarCalibracao();
      } 
      else if (cmd == 'H') {
        // No modo calibração, H define a posição atual como o ZERO (0,0)
        motorX->setCurrentPosition(0);
        motorY->setCurrentPosition(0);
        if (debugAtivo) Serial.println("[DEBUG] Zero redefinido na posição atual");
        Serial.println("ZERO DEFINIDO (0,0)");
      }
    }
  }
}

long coordParaPassos(int c) {
  long passos = (long)(c - OFFSET) * STEPS_PER_SQUARE;
  if (debugAtivo) {
    Serial.print("[DEBUG] Coord: ");
    Serial.print(c);
    Serial.print(" -> Passos: ");
    Serial.println(passos);
  }
  return passos;
}

void moverParaPassos(long alvoX, long alvoY) {
  long posAtualX = motorX->getCurrentPosition();
  long posAtualY = motorY->getCurrentPosition();

  long deltaX = abs(alvoX - posAtualX);
  long deltaY = abs(alvoY - posAtualY);

  if (debugAtivo) {
    Serial.print("[DEBUG] Mover: (");
    Serial.print(posAtualX);
    Serial.print(",");
    Serial.print(posAtualY);
    Serial.print(") -> (");
    Serial.print(alvoX);
    Serial.print(",");
    Serial.print(alvoY);
    Serial.print(") | Delta: ");
    Serial.print(deltaX);
    Serial.print(",");
    Serial.println(deltaY);
  }

  if (deltaX == 0 && deltaY == 0) return;

  float vX = VELOCIDADE_MAX_BASE;
  float vY = VELOCIDADE_MAX_BASE;
  float aX = ACELERACAO_MAX_BASE;
  float aY = ACELERACAO_MAX_BASE;

  if (deltaX > deltaY && deltaY > 0) {
    float proporcao = (float)deltaY / (float)deltaX;
    vX = VELOCIDADE_MAX_BASE;
    vY = VELOCIDADE_MAX_BASE * proporcao;
    aX = ACELERACAO_MAX_BASE;
    aY = ACELERACAO_MAX_BASE * proporcao;
  } 
  else if (deltaY > deltaX && deltaX > 0) {
    float proporcao = (float)deltaX / (float)deltaY;
    vX = VELOCIDADE_MAX_BASE * proporcao;
    vY = VELOCIDADE_MAX_BASE;
    aX = ACELERACAO_MAX_BASE * proporcao;
    aY = ACELERACAO_MAX_BASE;
  }

  if (debugAtivo) {
    Serial.print("[DEBUG] Velocidades (Hz): X=");
    Serial.print(vX);
    Serial.print(", Y=");
    Serial.println(vY);
  }

  motorX->setSpeedInHz(vX);
  motorX->setAcceleration(aX);
  motorY->setSpeedInHz(vY);
  motorY->setAcceleration(aY);

  motorX->moveTo(alvoX);
  motorY->moveTo(alvoY);

  while (motorX->isRunning() || motorY->isRunning()) { }
}

void processarTrajetoria() {
  int n = Serial.parseInt();
  if (debugAtivo) {
    Serial.print("[DEBUG] Trajetoria: ");
    Serial.print(n);
    Serial.println(" pontos");
  }
  
  // Confirma recepção e avisa que está pronto para receber os pontos
  Serial.println("READY_FOR_POINTS");

  digitalWrite(PIN_SLEEP, LOW);
  delay(2); // Tempo para o driver acordar

  for (int i = 0; i < n; i++) {
    // Aguarda até que os dados do ponto atual estejam disponíveis
    while (Serial.available() == 0) { }

    int x = Serial.parseInt();
    int y = Serial.parseInt();
    long stepX = coordParaPassos(x);
    long stepY = coordParaPassos(y);

    if (debugAtivo) {
      Serial.print("[DEBUG] Ponto ");
      Serial.print(i + 1);
      Serial.print(": (");
      Serial.print(x);
      Serial.print(",");
      Serial.print(y);
      Serial.println(")");
    }

    if (i == 0) {
      moverParaPassos(stepX, stepY);
      setServo(40);
      delay(800);
    } else {
      moverParaPassos(stepX, stepY);
    }

    // Confirma que o ponto foi processado para liberar o envio do próximo
    Serial.println("POINT_OK");
  }
  setServo(180);
  delay(800);

  digitalWrite(PIN_SLEEP, HIGH);
  Serial.println("TRAJETORIA OK");
}

void processarCalibracao() {
  long sx = Serial.parseInt();
  long sy = Serial.parseInt();
  
  if (debugAtivo) {
    Serial.print("[DEBUG] Move Relativo (K): X=");
    Serial.print(sx);
    Serial.print(", Y=");
    Serial.println(sy);
  }

  digitalWrite(PIN_SLEEP, LOW);
  delay(2); // Tempo para o driver acordar

  motorX->move(sx);
  motorY->move(sy);
  while (motorX->isRunning() || motorY->isRunning()) { }

  digitalWrite(PIN_SLEEP, HIGH);
  Serial.println("CALIBRACAO OK");
}
