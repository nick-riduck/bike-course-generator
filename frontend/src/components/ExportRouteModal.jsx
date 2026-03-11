import React, { useState, useEffect } from 'react';

const ExportRouteModal = ({ 
    isOpen, 
    onClose, 
    onExport,
    initialTitle = ''
}) => {
    const [fileName, setFilename] = useState('');
    const [format, setFormat] = useState('gpx');

    useEffect(() => {
        if (isOpen) {
            setFilename(initialTitle || 'Route');
            setFormat('gpx');
        }
    }, [isOpen, initialTitle]);

    const handleExport = () => {
        // Filename validation?
        if (!fileName.trim()) {
            alert("Please enter a filename.");
            return;
        }
        onExport(fileName.trim(), format);
        onClose();
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/80 backdrop-blur-sm animate-fadeIn" onClick={onClose}></div>
            
            {/* Modal Content */}
            <div className="relative bg-gray-900 border border-gray-800 rounded-3xl w-full max-w-sm shadow-2xl overflow-hidden animate-slideUp">
                {/* Header */}
                <div className="p-6 border-b border-gray-800 flex justify-between items-center">
                    <h2 className="text-xl font-black text-white">Export Route</h2>
                    <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Form Body */}
                <div className="p-6 space-y-6">
                    {/* Filename Input */}
                    <div className="space-y-2">
                        <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest px-1">File Name</label>
                        <input 
                            type="text"
                            value={fileName}
                            onChange={(e) => setFilename(e.target.value)}
                            placeholder="Enter filename..."
                            className="w-full bg-gray-800 text-white px-4 py-3 rounded-2xl border border-gray-700 focus:outline-none focus:border-routy-primary transition-all text-sm font-medium"
                            onKeyDown={(e) => e.key === 'Enter' && handleExport()}
                            autoFocus
                        />
                    </div>

                    {/* Format Selection */}
                    <div className="space-y-2">
                        <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest px-1">Format</label>
                        <div className="grid grid-cols-2 gap-3">
                            <button
                                onClick={() => setFormat('gpx')}
                                className={`py-3 rounded-2xl border transition-all flex flex-col items-center gap-1 ${
                                    format === 'gpx' 
                                    ? 'bg-blue-600/10 border-blue-500 text-blue-500' 
                                    : 'bg-gray-800/50 border-gray-700 text-gray-500 hover:border-gray-600'
                                }`}
                            >
                                <span className="text-lg font-black">GPX</span>
                                <span className="text-[10px] uppercase opacity-70">Universal</span>
                            </button>
                            <button
                                onClick={() => setFormat('tcx')}
                                className={`py-3 rounded-2xl border transition-all flex flex-col items-center gap-1 ${
                                    format === 'tcx' 
                                    ? 'bg-orange-600/10 border-orange-500 text-orange-500' 
                                    : 'bg-gray-800/50 border-gray-700 text-gray-500 hover:border-gray-600'
                                }`}
                            >
                                <span className="text-lg font-black">TCX</span>
                                <span className="text-[10px] uppercase opacity-70">Garmin / Wahoo</span>
                            </button>
                        </div>
                    </div>
                </div>

                {/* Footer Actions */}
                <div className="p-6 border-t border-gray-800 bg-gray-900/50 backdrop-blur-md">
                    <button 
                        onClick={handleExport}
                        className="w-full bg-white hover:bg-gray-200 text-black py-4 rounded-2xl font-black text-sm shadow-lg transition-all flex items-center justify-center gap-2 active:scale-[0.98]"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        DOWNLOAD FILE
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ExportRouteModal;