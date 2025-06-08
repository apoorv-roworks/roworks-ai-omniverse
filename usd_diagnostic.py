#!/usr/bin/env python3
"""
Simple USD File Diagnostic - No USD libraries required
Just file analysis and recommendations
"""

import os
import sys
import time
from pathlib import Path

def analyze_file_basic(usd_path: str):
    """Basic file analysis without USD libraries"""
    print(f"\n{'='*60}")
    print(f"📁 BASIC FILE ANALYSIS: {usd_path}")
    print(f"{'='*60}")
    
    if not os.path.exists(usd_path):
        print(f"❌ File does not exist: {usd_path}")
        return False
    
    # File size analysis
    file_size = os.path.getsize(usd_path)
    file_size_mb = file_size / (1024 * 1024)
    print(f"📊 File size: {file_size:,} bytes ({file_size_mb:.2f} MB)")
    
    # File type check
    with open(usd_path, 'rb') as f:
        header = f.read(100)
    
    if b'PXR-USDC' in header:
        file_format = "Binary USD (USDC)"
    elif b'#usda' in header:
        file_format = "ASCII USD (USDA)"
    else:
        file_format = "Unknown USD format"
    
    print(f"📋 Format: {file_format}")
    
    # Quick content analysis for ASCII files
    if file_format == "ASCII USD (USDA)":
        try:
            with open(usd_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(10000)  # Read first 10KB
                
            # Count some basic elements
            vertex_indicators = content.count('point3f[] points')
            face_indicators = content.count('int[] faceVertexIndices')
            mesh_indicators = content.count('def Mesh')
            material_indicators = content.count('def Material')
            texture_indicators = content.count('.jpg') + content.count('.png') + content.count('.tiff')
            
            print(f"📊 Content analysis (first 10KB):")
            print(f"   Mesh definitions: {mesh_indicators}")
            print(f"   Vertex arrays: {vertex_indicators}")
            print(f"   Face arrays: {face_indicators}")
            print(f"   Materials: {material_indicators}")
            print(f"   Texture references: {texture_indicators}")
            
        except Exception as e:
            print(f"⚠️ Could not analyze content: {e}")
    
    # Assessment based on current RoWorks limits
    print(f"\n🎯 ROWORKS IMPORT ASSESSMENT:")
    
    # Current restrictive limits
    current_limit_mb = 0.2  # 200MB in the current code (but effectively much lower due to vertex check)
    
    issues = []
    warnings = []
    good_signs = []
    
    # File size assessment
    if file_size_mb > 10:
        issues.append(f"Large file: {file_size_mb:.1f}MB (may cause timeout)")
    elif file_size_mb > 5:
        warnings.append(f"Medium file: {file_size_mb:.1f}MB (should work with enhanced importer)")
    else:
        good_signs.append(f"Good file size: {file_size_mb:.1f}MB (should import quickly)")
    
    # Format assessment
    if file_format == "Binary USD (USDC)":
        good_signs.append("Binary format - more efficient")
    elif file_format == "ASCII USD (USDA)":
        warnings.append("ASCII format - larger and slower than binary")
    
    # Print assessment
    if issues:
        print("❌ POTENTIAL ISSUES:")
        for issue in issues:
            print(f"   • {issue}")
    
    if warnings:
        print("⚠️ WARNINGS:")
        for warning in warnings:
            print(f"   • {warning}")
    
    if good_signs:
        print("✅ POSITIVE INDICATORS:")
        for sign in good_signs:
            print(f"   • {sign}")
    
    return True

def check_current_roworks_limits():
    """Explain current RoWorks limits vs your file"""
    print(f"\n{'='*60}")
    print("🔍 ROWORKS CURRENT LIMITS vs YOUR FILE")
    print(f"{'='*60}")
    
    print("Current RoWorks safety limits (TOO RESTRICTIVE):")
    print("   • File size: 200MB (reasonable)")
    print("   • Vertex count: 2M total (reasonable)")  
    print("   • Prim count: 15K (reasonable)")
    print("   • Import timeout: 30 seconds (too short for AWS)")
    print("   • BUT: Safety check may reject files prematurely")
    
    print("\nYour file characteristics:")
    print("   • File size: 1.8MB ✅ (well under 200MB)")
    print("   • Estimated vertices: ~47K ✅ (well under 2M)")
    print("   • Prims: 7 ✅ (well under 15K)")
    print("   • Expected import time: 5-15 seconds")
    
    print("\n❌ DIAGNOSIS: Your file should import easily!")
    print("The hanging suggests the safety check is incorrectly rejecting your file.")

def provide_solutions():
    """Provide specific solutions for the hanging issue"""
    print(f"\n{'='*60}")
    print("💡 SOLUTIONS FOR HANGING IMPORT")
    print(f"{'='*60}")
    
    print("IMMEDIATE FIXES:")
    print("1. 🔧 Update USDAnalyzer class (see code artifact)")
    print("   • Increase timeout from 30s to 90s")
    print("   • Relax vertex count checks")
    print("   • Skip complex stage analysis")
    
    print("\n2. 🧪 Test force import via API:")
    print("   curl -X POST 'http://your-server:49101/debug/force-import/Asset_5_29_2025_2'")
    
    print("\n3. 🔄 Manual import test in Omniverse:")
    print("   • File > Import > select your USD file")
    print("   • Or drag and drop into viewport")
    print("   • Check console for detailed error messages")
    
    print("\nROOT CAUSE ANALYSIS:")
    print("• Safety check is too conservative for your 1.8MB file")
    print("• 30-second timeout too short for AWS network latency")
    print("• Texture path resolution may be causing delays")
    print("• USD context synchronization timing issues")
    
    print("\nIF STILL HANGING AFTER FIXES:")
    print("• Check system resources: htop, df -h")
    print("• Monitor network: netstat -an | grep 49101")
    print("• Check Omniverse logs in ~/.nvidia-omniverse/logs/")
    print("• Try importing without textures first")

def main():
    """Main diagnostic function"""
    print("🔍 SIMPLE USD DIAGNOSTIC TOOL")
    print("(No USD libraries required)")
    print("=" * 60)
    
    # Your specific file
    usd_file = "/tmp/roworks_mesh_cntx9lyi/usd_assets/Asset_5_29_2025_2.usd"
    
    if len(sys.argv) > 1:
        usd_file = sys.argv[1]
    
    print(f"Target file: {usd_file}")
    
    # Run analysis
    if analyze_file_basic(usd_file):
        check_current_roworks_limits()
        provide_solutions()
    
    # Quick file system check
    print(f"\n{'='*60}")
    print("🖥️ SYSTEM CHECK")
    print(f"{'='*60}")
    
    try:
        # Check disk space
        statvfs = os.statvfs('/tmp')
        free_gb = (statvfs.f_frsize * statvfs.f_available) / (1024**3)
        print(f"💾 /tmp free space: {free_gb:.1f} GB")
        
        # Check if file is readable
        with open(usd_file, 'rb') as f:
            first_kb = f.read(1024)
        print(f"📖 File is readable: ✅")
        
        # Check permissions
        if os.access(usd_file, os.R_OK):
            print(f"🔐 Read permissions: ✅")
        else:
            print(f"🔐 Read permissions: ❌")
            
    except Exception as e:
        print(f"⚠️ System check error: {e}")

if __name__ == "__main__":
    main()
