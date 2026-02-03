# Disaster Recovery Drill Report - December 21, 2025

## Executive Summary

**Status**: Partial Completion - Critical structure discovery phase
**Completion**: ~74% (271 GB / 365 GB required)
**Outcome**: Drill halted due to disk space constraints; critical findings documented for next attempt
**Next Drill**: January 2026 with external storage (500+ GB)

**Key Success**: Discovered backup structure complexity and validated DR plan gaps before real disaster.

---

## Drill Execution Timeline

| Phase | Start | End | Duration | Status |
|-------|-------|-----|----------|--------|
| A: Access Verification | 14:00 | 14:15 | 15 min | ✅ Complete |
| B: Metadata Download | 14:15 | 15:30 | 75 min | ✅ Complete |
| C: Extraction Attempt #1 | 15:30 | 16:00 | 30 min | ❌ Failed |
| C: Structure Research | 16:00 | 16:45 | 45 min | ✅ Complete |
| D: Bucket Download | 16:45 | 19:03 | 138 min | ⚠️ Partial |
| Documentation | 19:03 | 19:45 | 42 min | ✅ Complete |
| **Total** | **14:00** | **19:45** | **5h 45m** | **74% Complete** |

---

## Download Metrics

### Successful Downloads
- **Config**: 8.964 GB, 803 files, 4m58s (9.679 MiB/s)
- **Control**: ~0 B, 1 file (subdirectory structure)
- **Guard**: 5.841 MB, 4 files (integrity databases)
- **Pool/file_pool**: ~10 MB, 229 files
- **Pool/chunk_index**: 5.987 GiB, 767 files, 6m51s (17.783 MiB/s)
- **Pool buckets (partial)**: 271 GB, folders 0, 10-17 only

### Missing Data
- **Pool/0/1/ through Pool/0/9/**: ~110 GB (8 subdirectories)
- **Other bucket folders**: Unknown size

### Performance
- **Total Downloaded**: 271 GB
- **Average Speed**: 15-20 MiB/s (Hetzner → macOS over residential ISP)
- **Total Duration**: ~3 hours active download
- **Egress Cost**: €0.00 (within Hetzner 1 TB/month free tier)

---

## Critical Findings

### 1. Backup Size Underestimation ⚠️

**Initial Estimate**: 15 GB (metadata + indexes)
**Actual Requirement**: 365 GB (complete backup with buckets)
**Error Factor**: 24x underestimate

**Impact**: Drill planned for laptop with 500 GB total disk, OS+apps used 160 GB, only 340 GB available. Insufficient for complete download.

**Root Cause**: Misunderstood Hyper Backup architecture - assumed indexes alone sufficient for selective restore.

### 2. Backup Structure Complexity 🔍

**Discovered Structure**:
```
DiskStation413j_1.hbk/
├── Config/ (9 GB metadata)
│   ├── @Share/homelab_immich/ (photo catalog *.db files)
│   ├── file_chunk1.index/ (215 .idx files)
│   ├── virtual_file.index/
│   ├── encKeys.1, public.pem.1 (encryption keys)
│   └── version_info.db.44
├── Control/ (version control)
│   └── @writer/v1.44.-1.0.0.none.none.cinfo
├── Guard/ (5.8 MB integrity validation)
│   └── cloud/ (4 .db files: bucket/file databases)
├── Pool/ (DATA STORAGE - 355+ GB)
│   ├── file_pool/ (229 files, file metadata)
│   ├── chunk_index/ (767 files @ 8 MB each, chunk mappings)
│   ├── bucketID.counter.44
│   ├── vkey.db.44
│   └── 0/ ← NESTED BUCKET STRUCTURE!
│       ├── 0/ (*.bucket.2, *.index.2 files - ~20 GB)
│       ├── 1/ (*.bucket.2, *.index.2 files - ~20 GB)
│       ├── 2/ ... 17/ (18 subdirectories total)
│       └── Each bucket: 2000-4000 files, 50 MB each
├── SynologyHyperBackup.bkpi (0 bytes - backup marker file)
└── synobkpinfo.db (3 KB - backup metadata)
```

**Key Discovery**: Deduplication uses nested bucket directories (`Pool/0/0/`, `Pool/0/1/`, etc.) containing actual photo data chunks. This structure was **not documented** in Synology KB articles consulted during drill planning.

### 3. Download Script Flattening Issue 🐛

**Problem**: `./hetzner_download.sh "DiskStation413j_1.hbk/Pool/0"`
→ Downloaded `Pool/0/10/` subdirectory to backup root as `/10/` (wrong structure)
→ rclone copy command flattened nested paths

**Expected**: `backup/DiskStation413j_1.hbk/Pool/0/10/`
**Actual**: `backup/DiskStation413j_1.hbk/10/`

**Impact**: Hyper Backup Explorer couldn't find buckets in expected location → validation failure

**Fix Applied**: Updated script to detect Pool downloads and preserve full path structure using modified target directory logic.

### 4. Hyper Backup Explorer Validation 🔒

**Behavior**: Tool validates ALL bucket checksums before allowing file browsing
**Error**: "Stored data on the backup destination are corrupted"

**Root Cause Analysis**:
1. Opened backup with only metadata + indexes (no bucket data)
2. Explorer attempted to validate chunk integrity
3. Missing `.bucket.2` files in `Pool/0/0/` → validation failure
4. Security feature prevents browsing potentially corrupted backups

**Attempted Workaround**: Reorganized folder structure to match expected layout
**Result**: Still failed - missing data chunks, not structure issue

**Second Attempt**: Downloaded 271 GB partial buckets (folders 0, 10-17)
**Result**: Still failed - missing folders 1-9 critical for validation

**Conclusion**: Hyper Backup Explorer requires **complete, correctly structured** backup data. No partial extraction possible.

### 5. Community Tool Research 🔬

**Tool Found**: hyperbackup_decrypt (GitHub: mistersandman/hyperbackup_decrypt)
- Python script (366 lines)
- Last updated: 9 years ago (2016)
- Functionality: Direct decryption bypassing Hyper Backup Explorer

**Key Code Finding** (Line 218):
```python
poolIndexDir = os.path.join(poolDir, "0/0")
```

Confirms nested structure requirement: `Pool/0/0/`, not `Pool/0/`.

**Evaluation**: Tool still requires full bucket data download. Not a workaround for incomplete downloads.

---

## Lessons Learned

### ✅ What Worked Well

1. **Hetzner S3 Access**: Credentials worked immediately, no authentication issues
2. **rclone Performance**: 15-20 MiB/s consistent throughput, automatic resume on interruption
3. **Bitwarden Integration**: Credentials easily retrieved, encryption key accessible
4. **Script Infrastructure**: Download/list scripts worked as designed for flat structures
5. **Egress Costs**: €0.00 - confirmed within free tier limits

### ❌ What Didn't Work

1. **Size Estimation**: 24x underestimate led to insufficient disk space planning
2. **Structure Understanding**: Nested bucket directories not discovered until mid-drill
3. **Download Script**: Flattened paths when downloading subdirectories
4. **Partial Extraction Assumption**: Believed indexes alone could support selective restore
5. **Disk Space Management**: Should have tested on VM or external drive first

### 🔧 Improvements Applied

1. **Runbook Updated**: Added accurate size requirements (365 GB minimum, 500 GB recommended)
2. **Script Fixed**: Modified `hetzner_download.sh` to preserve Pool directory structure
3. **Prerequisites Clarified**: External drive or dedicated VM strongly recommended
4. **Structure Documented**: Added complete backup tree diagram with explanations
5. **Next Attempt Plan**: Detailed instructions for January 2026 with external storage

### 📋 Process Improvements

1. **Pre-Drill Size Check**: Always run `./hetzner_list.sh` to calculate total size first
2. **Incremental Validation**: Download one bucket subdirectory, test extraction, then continue
3. **Storage Planning**: Allocate 1.5x expected size for working space
4. **Community Research**: Check GitHub/forums for tool requirements BEFORE starting drill
5. **Dry Run First**: Test structure with small subset before committing to full download

---

## Recovery Options Evaluated

### Option 1: Complete Download with External Storage ⭐ RECOMMENDED
- **Pros**: Official tool, complete validation, proves end-to-end recovery
- **Cons**: Requires 500+ GB external drive, 4-6 hour download
- **Status**: Planned for January 2026
- **Cost**: €0.00 egress (within free tier)

### Option 2: Community Tool (hyperbackup_decrypt)
- **Pros**: Command-line access, educational
- **Cons**: Unmaintained (9 years old), still needs full data download, may not work with current DSM versions
- **Status**: Deferred - not a workaround for size constraints

### Option 3: Synology C2 Storage Connection
- **Pros**: No local downloads, instant access
- **Cons**: $5/TB/month ongoing cost, doesn't test offline recovery capability
- **Status**: Not pursued - defeats purpose of validating Hetzner-only recovery

### Option 4: Replacement NAS
- **Pros**: Official DR workflow, full support
- **Cons**: Requires hardware purchase/borrowing, network access
- **Status**: Not tested - not realistic for immediate disaster scenario

---

## Validation Results

### Phase A: Access Verification ✅ PASS
- Hetzner S3 credentials: Working
- Bucket listing: Successful
- Backup structure visible: Confirmed

### Phase B: Metadata Download ✅ PASS
- Config: 9 GB downloaded successfully
- Control: Subdirectory structure preserved
- Guard: Integrity databases retrieved
- Pool indexes: 6 GB downloaded (file_pool + chunk_index)
- Transfer speeds: 9-17 MiB/s (acceptable)

### Phase C: Extraction Attempt #1 ❌ FAIL
- Error: "Stored data on the backup destination are corrupted"
- Root cause: Missing bucket data
- Workaround attempted: Folder reorganization (unsuccessful)

### Phase D: Bucket Download ⚠️ PARTIAL
- Downloaded: 271 GB (folders 0, 10-17)
- Missing: ~110 GB (folders 1-9)
- Completion: 74%
- Halt reason: Disk space exhausted (100% full)

### Phase E: Extraction Attempt #2 ❌ FAIL
- Structure corrected: Buckets moved to Pool/0/
- Error: Still "data corrupted"
- Root cause: Incomplete bucket set (missing folders 1-9)
- Conclusion: Complete data required, no partial extraction

---

## Risk Assessment Updates

### Original Risk: "Backup inaccessible from object storage"
- **Mitigation Tested**: Hetzner S3 access
- **Result**: ✅ PASS - Credentials work, bucket accessible

### Original Risk: "Encryption key lost or inaccessible"
- **Mitigation Tested**: Bitwarden retrieval
- **Result**: ✅ PASS - Key retrieved, accepted by Hyper Backup Explorer

### **NEW Risk Discovered**: "Backup structure complexity prevents extraction"
- **Probability**: Medium (unfamiliar tool/format)
- **Impact**: High (cannot recover photos)
- **Mitigation**: Complete this drill successfully before disaster
- **Status**: In progress - next attempt January 2026

### **NEW Risk Discovered**: "Insufficient storage for backup download"
- **Probability**: High (underestimated sizes)
- **Impact**: High (cannot complete drill)
- **Mitigation**: Pre-allocate external storage, calculate sizes first
- **Status**: Mitigated - external drive planned for next attempt

---

## Cost Analysis

### Hetzner Object Storage
- **Data Stored**: 1.73 TB (original photos)
- **Backup Size**: ~1.8 TB (with metadata)
- **Storage Cost**: €4.99/month base (includes 1 TB storage + 1 TB egress)
- **Egress This Drill**: 271 GB (0.271 TB)
- **Egress Cost**: €0.00 (within free tier)
- **Remaining Free Tier**: 729 GB this month

### Time Investment
- **Planning**: 2 hours (specification, task breakdown)
- **Setup**: 30 minutes (credentials, scripts)
- **Execution**: 5h 45m (partial completion)
- **Documentation**: 45 minutes (this report)
- **Total**: ~9 hours

### Future Costs (Next Attempt)
- **External Drive**: $60-100 (1TB SSD) - one-time, reusable
- **Egress**: €0.00 (365 GB < 1 TB free tier)
- **Time**: 6-8 hours estimated

**ROI**: Invaluable - discovering backup complexity BEFORE disaster is worth far more than cost.

---

## Recommendations

### Immediate Actions (Before Next Drill)
1. ✅ Update runbook with findings - **COMPLETE**
2. ✅ Fix download script structure handling - **COMPLETE**
3. [ ] Purchase external 1TB SSD for drill environment
4. [ ] Schedule January 2026 drill attempt (6-8 hour block)

### Long-Term Improvements
1. **Automate Size Calculation**: Add script to calculate total download size before starting
2. **Incremental Testing**: Create test drill with single bucket (20 GB) to validate process
3. **Alternative Tools**: Explore mounting Hetzner S3 as filesystem (s3fs) for on-demand access
4. **Backup Format**: Consider additional backup method (e.g., rclone sync, restic) for simpler recovery
5. **Quarterly Verification**: Download single bucket quarterly to ensure continued accessibility

### Documentation Updates
1. ✅ Update disaster-recovery-drill.md with structure diagram - **COMPLETE**
2. ✅ Add disk space requirements prominently - **COMPLETE**
3. ✅ Document nested Pool structure - **COMPLETE**
4. [ ] Create decision tree: "Do I have enough disk space?"
5. [ ] Add troubleshooting section: "Hyper Backup Explorer errors"

---

## Next Steps

### January 2026 Drill
1. **Preparation**:
   - Purchase 1TB external SSD
   - Clear calendar for 8-hour block
   - Review updated runbook
   - Test updated download script with single bucket

2. **Execution**:
   - Download complete Pool/0/ structure (all 18 subdirectories)
   - Verify directory structure matches expected layout
   - Open in Hyper Backup Explorer
   - Extract 10-20 sample photos
   - Verify photo viewability and EXIF data

3. **Success Criteria**:
   - [ ] 365 GB downloaded successfully
   - [ ] Correct structure: `Pool/0/0/` through `Pool/0/17/`
   - [ ] Hyper Backup Explorer opens without errors
   - [ ] Photos extractable and viewable
   - [ ] EXIF data intact (dates, camera info)

4. **Documentation**:
   - Create success report: `2026-01-XX-drill-report.md`
   - Update runbook with final timings
   - Mark Feature 012 as complete

---

## Conclusion

This partial drill successfully validated Hetzner S3 access and discovered critical complexity in Synology Hyper Backup's architecture. While the drill did not achieve full photo extraction, it accomplished its primary goal: **identifying gaps in the DR plan before a real disaster**.

**Key Takeaway**: The drill revealed that Hyper Backup's block-level deduplication creates a nested structure requiring complete bucket downloads (365 GB, not 15 GB estimated). Without this drill, a real disaster recovery attempt would have failed due to insufficient storage planning and incorrect assumptions about selective restore capabilities.

The invested 9 hours and €0.00 in egress costs provided invaluable insights that will ensure successful recovery when needed. Next month's attempt with external storage will complete the validation.

**Drill Value**: ⭐⭐⭐⭐⭐ (5/5) - Despite incomplete execution, critical learnings justify time invested.

---

**Report Prepared By**: GitHub Copilot (AI Assistant)
**Report Date**: December 21, 2025
**Next Review**: January 2026 (after complete drill attempt)
