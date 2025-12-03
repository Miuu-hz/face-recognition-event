#!/usr/bin/env python3
"""
GPU Detection Diagnostic Tool
Check if your system is configured correctly for GPU acceleration
"""
import subprocess
import sys

print("="*60)
print("GPU Detection Diagnostic")
print("="*60)

# 1. Check nvidia-smi
print("\n[1] Checking nvidia-smi...")
try:
    result = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=2)
    if result.returncode == 0:
        print("✅ nvidia-smi: GPU detected")
        # Show GPU info
        lines = result.stdout.split('\n')
        for line in lines:
            if 'NVIDIA' in line or 'GPU' in line:
                print(f"   {line.strip()}")
    else:
        print("❌ nvidia-smi: No GPU found")
except FileNotFoundError:
    print("❌ nvidia-smi: Command not found")
except Exception as e:
    print(f"❌ nvidia-smi: Error - {e}")

# 2. Check dlib installation
print("\n[2] Checking dlib installation...")
try:
    import dlib
    print("✅ dlib: Installed")
    print(f"   Version: {dlib.__version__ if hasattr(dlib, '__version__') else 'Unknown'}")
except ImportError:
    print("❌ dlib: Not installed")
    sys.exit(1)

# 3. Check dlib CUDA support (MOST IMPORTANT!)
print("\n[3] Checking dlib CUDA support...")
try:
    import dlib
    if hasattr(dlib, 'DLIB_USE_CUDA'):
        if dlib.DLIB_USE_CUDA:
            print("✅ dlib.DLIB_USE_CUDA: True (CUDA enabled)")
            print("   🎉 Your dlib is compiled with CUDA!")
        else:
            print("❌ dlib.DLIB_USE_CUDA: False (CUDA disabled)")
            print("   ⚠️  Your dlib is NOT compiled with CUDA!")
            print("   This is likely the problem!")
    else:
        print("❌ dlib.DLIB_USE_CUDA: Attribute not found")
        print("   ⚠️  Your dlib does not have CUDA support!")
        print("   This is likely the problem!")
except Exception as e:
    print(f"❌ Error checking CUDA: {e}")

# 4. Check face_recognition library
print("\n[4] Checking face_recognition library...")
try:
    import face_recognition
    print("✅ face_recognition: Installed")
except ImportError:
    print("❌ face_recognition: Not installed")

# 5. Current configuration from app.py
print("\n[5] Checking current app.py configuration...")
try:
    # Simulate the logic from app.py
    has_gpu = False

    # Method 1: Check dlib CUDA
    try:
        import dlib
        if hasattr(dlib, 'DLIB_USE_CUDA') and dlib.DLIB_USE_CUDA:
            has_gpu = True
    except:
        pass

    # Method 2: Check nvidia-smi
    if not has_gpu:
        try:
            result = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                has_gpu = True
        except:
            pass

    print(f"   detect_gpu() would return: {has_gpu}")

    default_model = 'cnn' if has_gpu else 'hog'
    print(f"   Selected model: {default_model.upper()}")

    if has_gpu and default_model == 'cnn':
        import dlib
        if not (hasattr(dlib, 'DLIB_USE_CUDA') and dlib.DLIB_USE_CUDA):
            print("\n   ⚠️⚠️⚠️  PROBLEM DETECTED! ⚠️⚠️⚠️")
            print("   GPU detected but dlib has no CUDA support")
            print("   → Will use CNN on CPU (VERY SLOW!)")
            print("   → This is why Ryzen+NVIDIA is slower than Intel!")

except Exception as e:
    print(f"❌ Error: {e}")

# Summary
print("\n" + "="*60)
print("SUMMARY")
print("="*60)

try:
    import dlib
    has_nvidia = False
    try:
        result = subprocess.run(['nvidia-smi'], capture_output=True, timeout=2)
        has_nvidia = result.returncode == 0
    except:
        pass

    has_dlib_cuda = hasattr(dlib, 'DLIB_USE_CUDA') and dlib.DLIB_USE_CUDA

    print(f"\nNVIDIA GPU: {'Yes' if has_nvidia else 'No'}")
    print(f"dlib CUDA: {'Yes' if has_dlib_cuda else 'No'}")

    if has_nvidia and not has_dlib_cuda:
        print("\n🔴 ISSUE FOUND:")
        print("   You have NVIDIA GPU but dlib is not compiled with CUDA")
        print("   This causes CNN model to run on CPU (10-50x slower!)")
        print("\n💡 SOLUTIONS:")
        print("   Option 1: Force use HOG model (add to .env)")
        print("             FACE_MODEL=hog")
        print("\n   Option 2: Recompile dlib with CUDA support")
        print("             (Advanced, see REQUIREMENTS.md)")
    elif has_dlib_cuda:
        print("\n✅ CONFIGURATION OK:")
        print("   dlib is properly configured with CUDA support")
        print("   CNN model will run on GPU (fast!)")
    else:
        print("\n✅ CONFIGURATION OK:")
        print("   No GPU, using HOG model on CPU (optimal for CPU-only)")

except Exception as e:
    print(f"\nError in summary: {e}")

print("\n" + "="*60)
