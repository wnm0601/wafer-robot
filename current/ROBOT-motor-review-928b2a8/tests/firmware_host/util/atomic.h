// PC 단일 스레드 시험 전용. 실제 원자성은 AVR 빌드/하드웨어 영역입니다.
#pragma once
#define ATOMIC_RESTORESTATE 0
#define ATOMIC_BLOCK(kind) for(bool once=true; once; once=false)
