// Mock Data for CloudDrive Picker
import { CloudFile, FileType } from './types';

export const MOCK_FILES: CloudFile[] = [
  // Root level folders
  {
    id: 'folder-1',
    name: 'Event Photos 2024',
    type: FileType.FOLDER,
    owner: 'You',
    modifiedAt: 'Dec 6, 2024',
    parentId: null
  },
  {
    id: 'folder-2',
    name: 'Wedding Photos',
    type: FileType.FOLDER,
    owner: 'You',
    modifiedAt: 'Dec 5, 2024',
    parentId: null
  },
  {
    id: 'folder-3',
    name: 'Corporate Events',
    type: FileType.FOLDER,
    owner: 'You',
    modifiedAt: 'Dec 4, 2024',
    parentId: null
  },

  // Files inside folder-1 (Event Photos 2024)
  {
    id: 'img-1',
    name: 'IMG_0001.jpg',
    type: FileType.IMAGE,
    size: '2.5 MB',
    owner: 'You',
    modifiedAt: 'Dec 6, 2024',
    thumbnailUrl: 'https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=300',
    parentId: 'folder-1'
  },
  {
    id: 'img-2',
    name: 'IMG_0002.jpg',
    type: FileType.IMAGE,
    size: '3.1 MB',
    owner: 'You',
    modifiedAt: 'Dec 6, 2024',
    thumbnailUrl: 'https://images.unsplash.com/photo-1511285560929-80b456fea0bc?w=300',
    parentId: 'folder-1'
  },
  {
    id: 'img-3',
    name: 'IMG_0003.jpg',
    type: FileType.IMAGE,
    size: '2.8 MB',
    owner: 'You',
    modifiedAt: 'Dec 6, 2024',
    thumbnailUrl: 'https://images.unsplash.com/photo-1519741497674-611481863552?w=300',
    parentId: 'folder-1'
  },
  {
    id: 'img-4',
    name: 'IMG_0004.jpg',
    type: FileType.IMAGE,
    size: '3.4 MB',
    owner: 'You',
    modifiedAt: 'Dec 6, 2024',
    thumbnailUrl: 'https://images.unsplash.com/photo-1533174072545-7a4b6ad7a6c3?w=300',
    parentId: 'folder-1'
  },
  {
    id: 'img-5',
    name: 'IMG_0005.jpg',
    type: FileType.IMAGE,
    size: '2.9 MB',
    owner: 'You',
    modifiedAt: 'Dec 6, 2024',
    thumbnailUrl: 'https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=300',
    parentId: 'folder-1'
  },

  // Files inside folder-2 (Wedding Photos)
  {
    id: 'img-6',
    name: 'Wedding_001.jpg',
    type: FileType.IMAGE,
    size: '4.2 MB',
    owner: 'You',
    modifiedAt: 'Dec 5, 2024',
    thumbnailUrl: 'https://images.unsplash.com/photo-1519741497674-611481863552?w=300',
    parentId: 'folder-2'
  },
  {
    id: 'img-7',
    name: 'Wedding_002.jpg',
    type: FileType.IMAGE,
    size: '3.8 MB',
    owner: 'You',
    modifiedAt: 'Dec 5, 2024',
    thumbnailUrl: 'https://images.unsplash.com/photo-1606216794074-735e91aa2c92?w=300',
    parentId: 'folder-2'
  },

  // Files inside folder-3 (Corporate Events)
  {
    id: 'img-8',
    name: 'Corporate_Meeting.jpg',
    type: FileType.IMAGE,
    size: '2.1 MB',
    owner: 'You',
    modifiedAt: 'Dec 4, 2024',
    thumbnailUrl: 'https://images.unsplash.com/photo-1511578314322-379afb476865?w=300',
    parentId: 'folder-3'
  }
];
