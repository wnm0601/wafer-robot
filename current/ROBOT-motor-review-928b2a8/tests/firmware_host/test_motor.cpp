// 실제 main.cpp를 포함하여 제어 분기/레지스터 쓰기를 시험. 포트 사용 없음.
#include <cassert>
#include <iostream>
#include "../../urt/mecanum_motor/src/main.cpp"

void assertOff() {
    assert((TCCR1A & (_BV(COM1A1)|_BV(COM1B1))) == 0);
    assert((TCCR5A & (_BV(COM5B1)|_BV(COM5C1))) == 0);
    assert(OCR1A==0 && OCR1B==0 && OCR5B==0 && OCR5C==0);
}

int main() {
    setup();
    assertOff();
    assert(PWM_PIN[0]==11 && PWM_PIN[1]==44 && PWM_PIN[2]==12 && PWM_PIN[3]==45);
    assert(DIR_PIN[0]==34 && DIR_PIN[1]==36 && DIR_PIN[2]==35 && DIR_PIN[3]==37);
    assert(ENC_A[0]==3 && ENC_A[1]==18 && ENC_A[2]==19 && ENC_A[3]==20);
    for(int i=0;i<4;i++) {
        assert(POS_TO_MOTOR[i]==i);
        assert(INVERT[i]==(i==1 || i==3));
    }
    handle(String("INFO"));
    assert(Serial.output.find("MECANUM_HKX_REVIEW_20261012")!=std::string::npos);
    for(int i=0;i<4;i++) {
        applyWheel(i,80);
        assert(pins[DIR_PIN[i]]==(INVERT[i]?LOW:HIGH));
        assert(OCR1A==(i==0 ? 80*PWM_TOP/255 : 0));
        assert(OCR5C==(i==1 ? 80*PWM_TOP/255 : 0));
        assert(OCR1B==(i==2 ? 80*PWM_TOP/255 : 0));
        assert(OCR5B==(i==3 ? 80*PWM_TOP/255 : 0));
        applyWheel(i,0);
        assert(pins[DIR_PIN[i]]==LOW);
        assertOff();
    }
    assert(rampToward(4,-80,8)==0);
    assert(rampToward(-4,80,8)==0);
    assert(rampToward(80,-80,8)==72);
    assert(rampToward(0,-80,8)==-8);
    for(int cur=-200;cur<=200;cur++) for(int goal=-200;goal<=200;goal++) {
        int next=rampToward(cur,goal,8);
        assert(abs(next-cur)<=8);
        assert(!(cur>0 && next<0) && !(cur<0 && next>0));
    }
    handle(String("M 1 40"));
    assert(target[0]==80 && target[1]==0 && target[2]==0 && target[3]==0);
    updateMotors();
    assert(OCR1A>0);
    handle(String("ESTOP"));
    assertOff();
    for(int i=0;i<4;i++) assert(current[i]==0 && target[i]==0 && pins[DIR_PIN[i]]==LOW);
    handle(String("P 2 4 -40"));
    assert(target[0]==0 && target[1]==-80 && target[2]==0 && target[3]==-80);
    handle(String("V 20 0 0"));
    for(int i=0;i<4;i++) assert(target[i]==40);
    handle(String("V 0 20 0"));
    assert(target[0]==40 && target[1]==-40 && target[2]==-40 && target[3]==40);
    for(const char* bad : {"M 1 20 extra", "M1 20", "M 1 99999999999999999", "M 5 20",
                          "P 1 1 20", "V 20 0", "V 101 0 0", "V 1 2 3extra", "garbage"}) {
        handle(String("M 1 20")); updateMotors();
        handle(String(bad)); assertOff();
        for(int i=0;i<4;i++) assert(current[i]==0 && target[i]==0);
    }
    pwrTrip=true;
    for(int i=0;i<4;i++) writePwm(i,80);
    assertOff();
    pwrTrip=false; pwrLatched=true;
    handle(String("M 1 20"));
    assert(target[0]==0);
    for(int i=0;i<4;i++) writePwm(i,80);
    assertOff();
    pwrLatched=false;
    pwmOutputsOn(); assertOff();
    handle(String("M 1 40")); updateMotors();
    fakeMillis=CMD_TIMEOUT_MS+1;
    loop();
    for(int i=0;i<4;i++) assert(target[i]==0);
    doEstop();
    for(int i=0;i<200;i++) Serial.input.push_back('a');
    pollSerial();
    assert(Serial.input.size()==152);  // 한 loop에서 48 bytes만 처리
    Serial.input.push_back('\n');
    while(Serial.available()) pollSerial();
    assertOff();
    assert(Serial.output.find("ERR LINE")!=std::string::npos);
    const char nulLine[] = "M 1 20\0hidden\n";
    for(size_t i=0;i<sizeof(nulLine)-1;i++) Serial.input.push_back(nulLine[i]);
    pollSerial();
    assertOff();
    assert(target[0]==0);
    std::cout<<"펌웨어 호스트 회귀시험 통과 (전기/기계 실측 아님)\n";
}
