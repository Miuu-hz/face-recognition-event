// Icon Component for File Types
import React from 'react';
import { FileType } from './types';
import {
  Folder,
  FileImage,
  FileVideo,
  FileText,
  File as FileIcon
} from 'lucide-react';

interface FileIconProps {
  type: FileType;
  className?: string;
}

export const FileIcon: React.FC<FileIconProps> = ({ type, className = "w-6 h-6" }) => {
  switch (type) {
    case FileType.FOLDER:
      return <Folder className={`${className} text-indigo-400`} />;
    case FileType.IMAGE:
      return <FileImage className={`${className} text-purple-400`} />;
    case FileType.VIDEO:
      return <FileVideo className={`${className} text-pink-400`} />;
    case FileType.DOCUMENT:
    case FileType.PDF:
      return <FileText className={`${className} text-blue-400`} />;
    case FileType.SPREADSHEET:
      return <FileText className={`${className} text-green-400`} />;
    default:
      return <FileIcon className={`${className} text-gray-400`} />;
  }
};
