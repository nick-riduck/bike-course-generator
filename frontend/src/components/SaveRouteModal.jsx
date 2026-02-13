import React, { useState, useEffect } from 'react';

const SaveRouteModal = ({ 
    isOpen, 
    onClose, 
    onSave, 
    initialData = {}, 
    isOwner = false,
    isLoading = false,
    isMapChanged = false
}) => {
    const [title, setTitle] = useState('');
    const [description, setDescription] = useState('');
    const [status, setStatus] = useState('PUBLIC');
    const [tags, setTags] = useState([]);
    const [tagInput, setTagInput] = useState('');

    useEffect(() => {
        if (isOpen) {
            setTitle(initialData.title || '');
            setDescription(initialData.description || '');
            setStatus(initialData.status || 'PUBLIC');
            setTags(initialData.tags || []);
        }
    }, [isOpen, initialData.id, initialData.updated_at]);

    // Check for changes to prevent unnecessary updates
    const hasChanges = React.useMemo(() => {
        if (isMapChanged) return true; // Map geometry changed

        const initTitle = initialData.title || '';
        const initDesc = initialData.description || '';
        const initStatus = initialData.status || 'PUBLIC';
        const initTags = initialData.tags || [];

        // Simple string comparisons
        if (title !== initTitle) return true;
        if (description !== initDesc) return true;
        if (status !== initStatus) return true;

        // Array comparison for tags (order doesn't matter for logic, but usually preserved)
        if (tags.length !== initTags.length) return true;
        const sortedTags = [...tags].sort();
        const sortedInitTags = [...initTags].sort();
        return JSON.stringify(sortedTags) !== JSON.stringify(sortedInitTags);
    }, [title, description, status, tags, initialData, isMapChanged]);

    const handleTagKeyDown = (e) => {
        if (e.nativeEvent.isComposing && e.key === 'Enter') return;

        if (e.key === 'Enter') {
            e.preventDefault();
            if (tagInput.trim() && !tags.includes(tagInput.trim())) {
                setTags([...tags, tagInput.trim()]);
                setTagInput('');
            }
        }
    };

    const handleTagChange = (e) => {
        const val = e.target.value;
        if (val.endsWith(' ')) {
            const newTag = val.trim();
            if (newTag && !tags.includes(newTag)) {
                setTags([...tags, newTag]);
            }
            setTagInput('');
        } else {
            setTagInput(val);
        }
    };

    const removeTag = (tagToRemove) => {
        setTags(tags.filter(t => t !== tagToRemove));
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/80 backdrop-blur-sm animate-fadeIn" onClick={onClose}></div>
            
            {/* Modal Content */}
            <div className="relative bg-gray-900 border border-gray-800 rounded-3xl w-full max-w-lg shadow-2xl overflow-hidden animate-slideUp">
                {/* Header */}
                <div className="p-6 border-b border-gray-800 flex justify-between items-center">
                    <h2 className="text-xl font-black text-white">Save Your Route</h2>
                    <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Form Body */}
                <div className="p-6 space-y-6 overflow-y-auto max-h-[70vh] custom-scrollbar">
                    {/* Title */}
                    <div className="space-y-2">
                        <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest px-1">Route Title</label>
                        <input 
                            type="text"
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            placeholder="Enter a title..."
                            className="w-full bg-gray-800 text-white px-4 py-3 rounded-2xl border border-gray-700 focus:outline-none focus:border-riduck-primary transition-all text-sm font-medium"
                        />
                    </div>

                    {/* Description */}
                    <div className="space-y-2">
                        <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest px-1">Description</label>
                        <textarea 
                            rows={3}
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="Tell more about this course..."
                            className="w-full bg-gray-800 text-white px-4 py-3 rounded-2xl border border-gray-700 focus:outline-none focus:border-riduck-primary transition-all text-sm font-medium resize-none"
                        />
                    </div>

                    {/* Privacy / Status */}
                    <div className="space-y-2">
                        <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest px-1">Visibility</label>
                        <div className="grid grid-cols-3 gap-2">
                            {[
                                { id: 'PUBLIC', label: 'Public', icon: '🌍' },
                                { id: 'LINK_ONLY', label: 'Link Only', icon: '🔗' },
                                { id: 'PRIVATE', label: 'Private', icon: '🔒' }
                            ].map(opt => (
                                <button
                                    key={opt.id}
                                    onClick={() => setStatus(opt.id)}
                                    className={`py-3 rounded-2xl border transition-all flex flex-col items-center gap-1 ${
                                        status === opt.id 
                                        ? 'bg-riduck-primary/10 border-riduck-primary text-riduck-primary' 
                                        : 'bg-gray-800/50 border-gray-700 text-gray-500 hover:border-gray-600'
                                    }`}
                                >
                                    <span className="text-lg">{opt.icon}</span>
                                    <span className="text-[10px] font-bold uppercase">{opt.label}</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Tags */}
                    <div className="space-y-2">
                        <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest px-1">Tags (Enter or Space)</label>
                        <div className="bg-gray-800 rounded-2xl border border-gray-700 p-2 min-h-[56px] flex flex-wrap gap-2">
                            {tags.map(tag => (
                                <span key={tag} className="bg-riduck-primary/20 text-riduck-primary px-3 py-1 rounded-full text-xs font-bold flex items-center gap-1 border border-riduck-primary/30">
                                    #{tag}
                                    <button onClick={() => removeTag(tag)} className="hover:text-white transition-colors">
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                                            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                                        </svg>
                                    </button>
                                </span>
                            ))}
                            <input 
                                type="text"
                                value={tagInput}
                                onChange={handleTagChange}
                                onKeyDown={handleTagKeyDown}
                                className="bg-transparent border-none focus:outline-none text-white text-sm flex-1 min-w-[80px] p-1"
                                placeholder={tags.length === 0 ? "Add tags like #gravel #climb..." : ""}
                            />
                        </div>
                    </div>
                </div>

                {/* Footer Actions */}
                <div className="p-6 border-t border-gray-800 bg-gray-900/50 backdrop-blur-md grid grid-cols-2 gap-3">
                    {/* Overwrite / Update Button */}
                    <button 
                        onClick={() => onSave({ title, description, status, tags, isOverwrite: true })}
                        disabled={isLoading || !isOwner || !initialData.id || !title.trim() || !hasChanges}
                        className={`py-4 rounded-2xl font-bold text-sm transition-all border flex items-center justify-center ${
                            !isOwner || !initialData.id || !hasChanges
                            ? 'bg-gray-800/30 text-gray-600 border-gray-800 cursor-not-allowed opacity-70' 
                            : 'bg-gray-800 hover:bg-gray-700 text-white border-gray-700'
                        }`}
                        title={
                            !isOwner ? "You can only update your own routes" : 
                            (!initialData.id ? "Save as new first" : 
                            (!hasChanges ? "No changes to update" : "Overwrite existing route"))
                        }
                    >
                        {hasChanges ? "Update Existing" : "No Changes"}
                    </button>

                    {/* Save as New / Fork Button */}
                    <button 
                        onClick={() => onSave({ title, description, status, tags, isOverwrite: false })}
                        disabled={isLoading || !title.trim()}
                        className="bg-riduck-primary hover:brightness-110 text-white py-4 rounded-2xl font-black text-sm shadow-lg shadow-riduck-primary/20 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
                    >
                        {isLoading ? (
                            <div className="animate-spin h-5 w-5 border-2 border-white rounded-full border-t-transparent"></div>
                        ) : (
                            initialData.id ? 'Fork as New' : 'Save to Cloud'
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default SaveRouteModal;