#pragma once
#define ATOMIC_RESTORESTATE 0
#define ATOMIC_BLOCK(unused) for (bool fake_atomic_once = true; fake_atomic_once; fake_atomic_once = false)
