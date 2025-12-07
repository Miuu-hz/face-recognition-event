// CloudDrive Picker with Futuristic Dark Theme
import React, { useState, useMemo, useEffect } from 'react';
import {
  X,
  Search,
  LayoutGrid,
  List as ListIcon,
  ChevronRight,
  Cloud,
  CheckCircle2,
  Filter,
  FolderOpen,
  Folder
} from 'lucide-react';
import { CloudFile, FileType, ViewMode, BreadcrumbItem } from './types';
import { MOCK_FILES } from './constants';
import { FileIcon } from './Icon';

interface CloudFilePickerProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (files: CloudFile[]) => void;
  maxSelections?: number;
  allowedTypes?: FileType[];
  selectFoldersOnly?: boolean;
}

export const CloudFilePicker: React.FC<CloudFilePickerProps> = ({
  isOpen,
  onClose,
  onSelect,
  maxSelections = 1,
  allowedTypes,
  selectFoldersOnly = true
}) => {
  const [currentPath, setCurrentPath] = useState<BreadcrumbItem[]>([{ id: null, name: 'My Drive' }]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [linkUrl, setLinkUrl] = useState('');

  // Reset state when opening
  useEffect(() => {
    if (isOpen) {
      setSelectedIds(new Set());
      setCurrentPath([{ id: null, name: 'My Drive' }]);
      setLinkUrl('');
    }
  }, [isOpen]);

  const currentFolderId = currentPath[currentPath.length - 1].id;

  // Filter files based on current folder or search term
  const filteredFiles = useMemo(() => {
    let files = MOCK_FILES;
    const searchTerm = linkUrl.trim().toLowerCase();

    if (searchTerm) {
      files = files.filter(f => f.name.toLowerCase().includes(searchTerm));
    } else {
      files = files.filter(f => f.parentId === currentFolderId);
    }

    // Sort: Folders first, then files
    return files.sort((a, b) => {
      if (a.type === FileType.FOLDER && b.type !== FileType.FOLDER) return -1;
      if (a.type !== FileType.FOLDER && b.type === FileType.FOLDER) return 1;
      return a.name.localeCompare(b.name);
    });
  }, [currentFolderId, linkUrl]);

  // Helper to get preview images for a folder
  const getFolderPreview = (folderId: string) => {
    const images = MOCK_FILES.filter(f => f.parentId === folderId && f.type === FileType.IMAGE);
    return {
      thumbnails: images.slice(0, 4).map(f => f.thumbnailUrl || ''),
      totalCount: images.length
    };
  };

  const handleNavigate = (folderId: string | null, folderName: string) => {
    setSelectedIds(new Set());
    setLinkUrl('');

    if (folderId === null) {
      setCurrentPath([{ id: null, name: 'My Drive' }]);
    } else {
      const existingIndex = currentPath.findIndex(p => p.id === folderId);
      if (existingIndex !== -1) {
        setCurrentPath(currentPath.slice(0, existingIndex + 1));
      } else {
        setCurrentPath([...currentPath, { id: folderId, name: folderName }]);
      }
    }
  };

  const handleFileClick = (file: CloudFile) => {
    if (file.type === FileType.FOLDER) {
      if (selectFoldersOnly) {
        toggleSelection(file.id);
      } else {
        handleNavigate(file.id, file.name);
      }
    } else {
      if (!selectFoldersOnly) {
         toggleSelection(file.id);
      }
    }
  };

  const handleFileDoubleClick = (file: CloudFile) => {
    if (file.type === FileType.FOLDER) {
      handleNavigate(file.id, file.name);
    }
  };

  const toggleSelection = (id: string) => {
    const newSet = new Set(selectedIds);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      if (maxSelections === 1) {
        newSet.clear();
      }
      if (newSet.size < maxSelections) {
        newSet.add(id);
      } else if (maxSelections === 1) {
          newSet.add(id);
      }
    }
    setSelectedIds(newSet);
  };

  const handleSubmit = () => {
    const selectedFiles = MOCK_FILES.filter(f => selectedIds.has(f.id));
    onSelect(selectedFiles);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{
      background: 'rgba(2, 6, 23, 0.6)',
      backdropFilter: 'blur(16px)'
    }}>
      <div className="w-full max-w-6xl h-[88vh] flex flex-col overflow-hidden rounded-2xl border shadow-2xl" style={{
        background: 'rgba(15, 23, 42, 0.95)',
        borderColor: '#1e293b',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 40px rgba(99, 102, 241, 0.15)'
      }}>

        {/* Header */}
        <div className="h-20 border-b flex items-center justify-between px-6 shrink-0 gap-6" style={{
          borderColor: '#1e293b',
          background: 'rgba(15, 23, 42, 0.8)',
          backdropFilter: 'blur(20px)'
        }}>
          <div className="flex items-center gap-3 shrink-0">
            <div className="w-11 h-11 rounded-xl flex items-center justify-center" style={{
              background: 'linear-gradient(135deg, #6366f1, #a855f7)',
              boxShadow: '0 8px 16px rgba(99, 102, 241, 0.3)'
            }}>
               <Cloud className="text-white w-6 h-6" />
            </div>
            <h2 className="text-xl font-bold" style={{ color: '#ffffff' }}>
                {selectFoldersOnly ? 'Select Folder' : 'Select Files'}
            </h2>
          </div>

          <div className="flex-1 max-w-2xl relative group">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 transition-colors" style={{
              color: '#64748b'
            }} />
            <input
              type="text"
              placeholder="Search folders or paste Google Drive link..."
              className="w-full pl-12 pr-4 py-3 rounded-xl transition-all border text-base outline-none"
              style={{
                background: 'rgba(30, 41, 59, 0.5)',
                borderColor: '#1e293b',
                color: '#ffffff'
              }}
              value={linkUrl}
              onChange={(e) => setLinkUrl(e.target.value)}
            />
             {linkUrl && (
                <button
                  onClick={() => setLinkUrl('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-full transition-colors"
                  style={{
                    color: '#94a3b8'
                  }}
                >
                    <X className="w-4 h-4" />
                </button>
             )}
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-full transition-colors shrink-0"
            style={{ color: '#94a3b8' }}
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Main Body */}
        <div className="flex flex-1 overflow-hidden">

          {/* Content Area */}
          <div className="flex-1 flex flex-col min-w-0">

            {/* Toolbar / Breadcrumbs */}
            <div className="h-16 border-b flex items-center justify-between px-6 shrink-0 z-10" style={{
              borderColor: '#1e293b',
              background: 'rgba(15, 23, 42, 0.6)',
              backdropFilter: 'blur(20px)'
            }}>
              <div className="flex items-center gap-1 text-sm overflow-x-auto no-scrollbar" style={{ color: '#94a3b8' }}>
                  {linkUrl ? (
                    <div className="flex items-center gap-2 font-medium px-1" style={{ color: '#e2e8f0' }}>
                        <Search className="w-4 h-4" style={{ color: '#64748b' }} />
                        Search results for "{linkUrl}"
                    </div>
                  ) : (
                    currentPath.map((item, index) => (
                      <React.Fragment key={item.id || 'root'}>
                        {index > 0 && <ChevronRight className="w-4 h-4 flex-shrink-0" style={{ color: '#64748b' }} />}
                        <button
                          onClick={() => handleNavigate(item.id, item.name)}
                          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap ${index === currentPath.length - 1 ? 'font-semibold pointer-events-none' : ''}`}
                          style={{
                            color: index === currentPath.length - 1 ? '#ffffff' : '#94a3b8',
                            background: index === currentPath.length - 1 ? 'rgba(99, 102, 241, 0.15)' : 'transparent'
                          }}
                        >
                          {index === 0 && <FolderOpen className="w-4 h-4" style={{ color: '#6366f1' }} />}
                          {item.name}
                        </button>
                      </React.Fragment>
                    ))
                  )}
              </div>

              <div className="flex items-center gap-2 border-l pl-4 ml-4" style={{ borderColor: '#1e293b' }}>
                <button
                    onClick={() => setViewMode('list')}
                    className={`p-2 rounded-lg transition-all`}
                    style={{
                      background: viewMode === 'list' ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                      color: viewMode === 'list' ? '#6366f1' : '#64748b'
                    }}
                >
                  <ListIcon className="w-5 h-5" />
                </button>
                <button
                    onClick={() => setViewMode('grid')}
                    className={`p-2 rounded-lg transition-all`}
                    style={{
                      background: viewMode === 'grid' ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                      color: viewMode === 'grid' ? '#6366f1' : '#64748b'
                    }}
                >
                  <LayoutGrid className="w-5 h-5" />
                </button>
                <button className="p-2 rounded-lg ml-1 transition-colors" style={{ color: '#64748b' }}>
                    <Filter className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* File View */}
            <div className="flex-1 overflow-y-auto p-6">
                {filteredFiles.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center" style={{ color: '#64748b' }}>
                        <div className="w-24 h-24 rounded-full flex items-center justify-center mb-4" style={{
                          background: 'rgba(30, 41, 59, 0.5)'
                        }}>
                            {linkUrl ? <Search className="w-10 h-10" style={{ color: '#475569' }} /> : <FolderOpen className="w-10 h-10" style={{ color: '#475569' }} />}
                        </div>
                        <p className="text-lg font-medium" style={{ color: '#94a3b8' }}>
                            {linkUrl ? 'No folders or files found' : 'Folder is empty'}
                        </p>
                    </div>
                ) : (
                    <div className={
                        viewMode === 'grid'
                        ? "grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4"
                        : "flex flex-col gap-1"
                    }>
                        {filteredFiles.map((file) => {
                            const previewData = file.type === FileType.FOLDER ? getFolderPreview(file.id) : undefined;

                            return (
                                <FileItem
                                    key={file.id}
                                    file={file}
                                    viewMode={viewMode}
                                    isSelected={selectedIds.has(file.id)}
                                    onSelect={() => handleFileClick(file)}
                                    onDoubleClick={() => handleFileDoubleClick(file)}
                                    previewImages={previewData?.thumbnails}
                                    totalCount={previewData?.totalCount}
                                    isDisabled={selectFoldersOnly && file.type !== FileType.FOLDER}
                                />
                            );
                        })}
                    </div>
                )}
            </div>

          </div>
        </div>

        {/* Footer */}
        <div className="h-24 border-t flex items-center justify-between px-8 shrink-0" style={{
          borderColor: '#1e293b',
          background: 'rgba(15, 23, 42, 0.8)',
          backdropFilter: 'blur(20px)'
        }}>
          <div className="text-sm">
             {selectedIds.size > 0 ? (
                 <span className="flex items-center gap-2 font-medium px-4 py-2 rounded-full border" style={{
                   color: '#6366f1',
                   background: 'rgba(99, 102, 241, 0.15)',
                   borderColor: '#6366f1'
                 }}>
                     <CheckCircle2 className="w-4 h-4" />
                     {selectedIds.size} {selectFoldersOnly ? 'folder' : 'file'}{selectedIds.size !== 1 ? 's' : ''} selected
                 </span>
             ) : (
                 <span style={{ color: '#64748b' }}>No items selected</span>
             )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-8 py-3 rounded-xl text-sm font-medium transition-colors"
              style={{ color: '#94a3b8' }}
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={selectedIds.size === 0 && !linkUrl}
              className="px-10 py-3 rounded-xl text-sm font-medium text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: selectedIds.size === 0 && !linkUrl ? '#334155' : 'linear-gradient(135deg, #6366f1, #a855f7)',
                boxShadow: selectedIds.size === 0 && !linkUrl ? 'none' : '0 8px 16px rgba(99, 102, 241, 0.3)'
              }}
            >
              Select
            </button>
          </div>
        </div>

      </div>
    </div>
  );
};

interface FileItemProps {
  file: CloudFile;
  viewMode: ViewMode;
  isSelected: boolean;
  onSelect: () => void;
  onDoubleClick: () => void;
  previewImages?: string[];
  totalCount?: number;
  isDisabled?: boolean;
}

const FileItem: React.FC<FileItemProps> = ({
    file,
    viewMode,
    isSelected,
    onSelect,
    onDoubleClick,
    previewImages,
    totalCount,
    isDisabled
}) => {
  if (viewMode === 'list') {
    return (
      <div
        onClick={(e) => {
            if (isDisabled) return;
            e.stopPropagation();
            onSelect();
        }}
        onDoubleClick={(e) => {
            e.stopPropagation();
            onDoubleClick();
        }}
        className={`group flex items-center gap-4 p-3 rounded-xl cursor-pointer transition-colors border-b ${
          isDisabled ? 'opacity-50 grayscale cursor-default' : ''
        }`}
        style={{
          background: isSelected ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
          borderColor: '#1e293b'
        }}
      >
        <div className="w-10 flex justify-center">
            <FileIcon type={file.type} className="w-6 h-6" />
        </div>
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-medium truncate`} style={{ color: isSelected ? '#6366f1' : '#e2e8f0' }}>{file.name}</p>
        </div>
        <div className="w-32 text-xs hidden sm:block" style={{ color: '#94a3b8' }}>
            {file.owner}
        </div>
        <div className="w-32 text-xs hidden sm:block" style={{ color: '#94a3b8' }}>
          {file.modifiedAt}
        </div>
        <div className="w-20 text-xs text-right" style={{ color: '#64748b' }}>
          {file.type !== FileType.FOLDER ? file.size : `${totalCount || 0} items`}
        </div>
      </div>
    );
  }

  // Grid View
  const isFolder = file.type === FileType.FOLDER;

  return (
    <div
      onClick={(e) => {
        if (isDisabled) return;
        e.stopPropagation();
        onSelect();
      }}
      onDoubleClick={(e) => {
        e.stopPropagation();
        onDoubleClick();
      }}
      className={`group relative flex flex-col rounded-2xl border transition-all duration-200 ${
        isDisabled ? 'opacity-60 cursor-default' : 'cursor-pointer'
      }`}
      style={{
        background: isSelected ? 'rgba(99, 102, 241, 0.15)' : 'rgba(30, 41, 59, 0.5)',
        borderColor: isSelected ? '#6366f1' : '#1e293b',
        boxShadow: isSelected ? '0 0 0 2px rgba(99, 102, 241, 0.5)' : 'none'
      }}
    >
      {/* Selection Checkmark */}
      {isSelected && (
          <div className="absolute top-3 left-3 z-10 rounded-full text-white p-0.5 shadow-sm" style={{
            background: '#6366f1'
          }}>
              <CheckCircle2 className="w-4 h-4" />
          </div>
      )}

      {/* Preview Area */}
      <div className={`aspect-[4/3] w-full rounded-t-2xl overflow-hidden flex items-center justify-center relative border-b`} style={{
        background: isFolder ? 'rgba(30, 41, 59, 0.6)' : 'rgba(15, 23, 42, 0.8)',
        borderColor: '#1e293b'
      }}>

        {isFolder && previewImages && previewImages.length > 0 ? (
            <div className="grid grid-cols-2 grid-rows-2 w-full h-full gap-0.5 p-0.5 box-border">
                <div className="overflow-hidden relative" style={{ background: 'rgba(30, 41, 59, 0.6)' }}>
                    {previewImages[0] && <img src={previewImages[0]} className="w-full h-full object-cover" alt="" />}
                </div>
                <div className="overflow-hidden relative" style={{ background: 'rgba(30, 41, 59, 0.6)' }}>
                    {previewImages[1] && <img src={previewImages[1]} className="w-full h-full object-cover" alt="" />}
                </div>
                <div className="overflow-hidden relative" style={{ background: 'rgba(30, 41, 59, 0.6)' }}>
                    {previewImages[2] && <img src={previewImages[2]} className="w-full h-full object-cover" alt="" />}
                </div>
                <div className="overflow-hidden relative" style={{ background: 'rgba(30, 41, 59, 0.6)' }}>
                    {previewImages[3] && <img src={previewImages[3]} className="w-full h-full object-cover" alt="" />}
                    {(totalCount || 0) > 4 && (
                        <div className="absolute inset-0 flex items-center justify-center" style={{ background: 'rgba(0, 0, 0, 0.7)' }}>
                            <span className="text-white font-bold text-xs">+{ (totalCount || 0) - 4 }</span>
                        </div>
                    )}
                </div>
            </div>
        ) : file.type === FileType.IMAGE && file.thumbnailUrl ? (
          <img src={file.thumbnailUrl} alt={file.name} className="w-full h-full object-cover" />
        ) : (
           <div className={`p-5 rounded-2xl`} style={{
             background: file.type === FileType.FOLDER ? 'transparent' : 'rgba(30, 41, 59, 0.8)'
           }}>
              <FileIcon type={file.type} className={file.type === FileType.FOLDER ? "w-12 h-12" : "w-10 h-10"} />
           </div>
        )}

        {!isDisabled && (
            <div className={`absolute inset-0 transition-colors`} style={{
              background: isSelected ? 'rgba(99, 102, 241, 0.1)' : 'transparent'
            }} />
        )}
      </div>

      {/* Info Area */}
      <div className="p-4 flex items-start gap-3">
        <div className="mt-0.5 shrink-0">
            {isFolder ? <Folder className="w-4 h-4" style={{ color: '#6366f1' }} /> : <FileIcon type={file.type} className="w-4 h-4" />}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium truncate" title={file.name} style={{ color: '#e2e8f0' }}>
            {file.name}
          </p>
          <div className="flex items-center gap-2 mt-1.5">
             <span className="text-xs font-medium" style={{ color: '#64748b' }}>
                {isFolder ? `${totalCount || 0} items` : file.size}
             </span>
          </div>
        </div>
      </div>
    </div>
  );
};
